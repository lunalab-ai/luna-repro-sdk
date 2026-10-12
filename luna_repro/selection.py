"""Local candidate selection and immutable review bundles; no implicit remote calls."""
from dataclasses import dataclass, field
import copy
import hashlib
import html
import inspect
import json
import os
from pathlib import Path
import re
import sys
from uuid import UUID

from . import adapters, session
from .client import Page, PublishError, _atomic_write, _checked_bundle, _json, _pending, _source, _text, publish_bundle

MAX_CANDIDATES = 100
MAX_NAMESPACE = 1000


def _registration(frame):
    filename = frame.f_code.co_filename
    if filename.startswith("<"):
        # IPython execution counters are not stable Jupyter/Colab cell IDs.
        return {}
    return {"file": Path(filename).name, "line_start": frame.f_lineno,
            "provenance": {"schema": "luna.repro.source.v1", "role": "registration", "provider": "python"}}


@dataclass
class Candidate:
    name: str
    kind: str
    summary: dict
    recommended: bool
    reason: str
    value: object = field(repr=False)
    source: dict = field(default_factory=dict, repr=False)
    options: dict = field(default_factory=dict)
    title: str = ""
    description: str = ""


def _candidate(name, value, source, *, explicit=False):
    found = adapters.identify(value)
    if explicit and type(value) is str:
        found = ("text", {"kind": "text", "characters": len(value)}, True, "Explicit text / 명시한 텍스트")
    if explicit and type(value) is bytes:
        found = ("image_bytes", {"kind": "image_bytes", "bytes": len(value)}, True, "Explicit PNG/JPEG / 명시한 이미지")
    if found is None:
        return None
    kind, summary, recommended, reason = found
    if not explicit and kind == "scalar" and name.casefold() in {
            "i", "j", "k", "idx", "index", "epoch", "epochs", "batch_size", "learning_rate", "lr",
            "seed", "random_seed", "step", "steps", "num_epochs", "max_epochs", "num_workers",
            "iteration", "iterations", "batch", "batch_index"}:
        recommended = False
        reason = "Likely setting/loop variable; available but unchecked / 설정·반복 변수로 보여 기본 선택 해제"
    return Candidate(name, kind, summary, recommended, reason, value, _source(source), title=name)


class Selection:
    """Review locally, then explicitly publish the exact frozen selection.

    Editing selection/options invalidates the prior review. Mutating original
    objects after preview never changes the already frozen bundle.
    """
    def __init__(self, candidates, *, project=None, title="Research results", description="", purpose=""):
        self.candidates = {item.name: item for item in candidates}
        configured = session.current()
        self.project = str(UUID(str(project))) if project else configured.project if configured else None
        self.title, self.description = _text(title, 300, required=True), _text(description, 12000)
        self.purpose = _text(purpose, 1000)
        self.selected = [item.name for item in candidates if item.recommended]
        self._frozen = None
        self._last_receipt = None
        self._widget = None

    def __repr__(self):
        return f"Selection(candidates={len(self.candidates)}, selected={len(self.selected)}, reviewed={self._frozen is not None})"

    def summary(self):
        """Metadata only, kept local. Calling this never requests AI analysis."""
        return [{"name": item.name, **item.summary, "recommended": item.recommended, "reason": item.reason}
                for item in self.candidates.values()]

    @property
    def receipt(self):
        """Last explicit/opted-in send outcome, or None before a send."""
        return copy.deepcopy(self._last_receipt)

    def choose(self, *names):
        if not names or len(set(names)) != len(names) or any(type(n) is not str or n not in self.candidates for n in names):
            raise ValueError("Choose one or more unique candidate names from selection.summary().")
        self.selected = list(names)
        self._frozen = None
        return self

    def edit(self, *, title=None, description=None, order=None):
        if title is not None:
            self.title = _text(title, 300, required=True)
        if description is not None:
            self.description = _text(description, 12000)
        if order is not None:
            if type(order) not in {list, tuple} or len(order) != len(self.selected) or set(order) != set(self.selected):
                raise ValueError("Order must contain every selected name exactly once.")
            self.selected = list(order)
        self._frozen = None
        return self

    def option(self, name, *, title=None, description=None, **options):
        if name not in self.candidates:
            raise ValueError("Unknown candidate name.")
        item = self.candidates[name]
        # Only bounded JSON options; no arbitrary serializer or callable options.
        raw = json.dumps(options, allow_nan=False)
        if len(raw) > 8192:
            raise ValueError("Conversion options exceed the limit.")
        item.options.update(json.loads(raw))
        if title is not None:
            item.title = _text(title, 300, required=True)
        if description is not None:
            item.description = _text(description, 12000)
        self._frozen = None
        return self

    def _freeze(self):
        if self._frozen is not None:
            return self._frozen
        configured = session.current()
        project = self.project or (configured.project if configured else None)
        if not project:
            raise ValueError("Candidates remain local. Run configure(project=...) or connect(project=...) before preview/save/send.")
        if not self.selected:
            raise ValueError("Select at least one result before previewing.")
        token = configured.token if configured and configured.project == project else None
        page = Page(project, self.title, description=self.description, token=token)
        for name in self.selected:
            item = self.candidates[name]
            key = "result-" + hashlib.sha256(name.encode()).hexdigest()[:16]
            section = page.section(key, item.title, description=item.description, source=item.source)
            adapters.convert(section, item.value, item.kind, item.options)
        self._frozen = page.bundle()
        self.project = project
        return self._frozen

    def bundle(self):
        return copy.deepcopy(self._freeze())

    def preview(self, path=None):
        """Render frozen selected values locally. No project authorization or upload."""
        document = _preview(self._freeze())
        if path is not None:
            _atomic_write(path, document.encode("utf-8"))
        return document

    def save(self, path):
        return _atomic_write(path, _checked_bundle(self._freeze()))

    def publish(self, *, strict=False, timeout=30):
        """Explicit send. Repeat calls reuse request identity and exact reviewed bytes."""
        bundle = self._freeze()
        configured = session.current()
        if configured and configured.project != bundle["project_id"]:
            raise ValueError("Configured project changed after selection; reconnect the reviewed project.")
        endpoint, token = (configured.endpoint, configured.token) if configured else (None, None)
        data = _checked_bundle(bundle)
        for secret in (token, os.environ.get("LUNA_REPRO_TOKEN")):
            if secret and secret.encode() in data:
                raise ValueError("A configured credential appears in selected results.")
        outbox = Path(configured.outbox) if configured and configured.outbox else Path(".luna-repro") / "outbox"
        pending = outbox / (bundle["request_id"] + ".json")
        _atomic_write(pending, data)
        try:
            receipt = publish_bundle(bundle, endpoint=endpoint, token=token, timeout=timeout)
        except (PublishError, ValueError) as error:
            if strict:
                raise
            self._last_receipt = {**_pending(bundle, error), "outbox_path": str(pending)}
            return copy.deepcopy(self._last_receipt)
        _atomic_write(outbox / (bundle["request_id"] + ".receipt.json"), _json(receipt))
        self._last_receipt = receipt
        return receipt

    def save_rule(self, path, *, auto_publish=False):
        if type(auto_publish) is not bool or not self.selected:
            raise ValueError("Choose results and an explicit boolean auto_publish policy.")
        project = self.project or (session.current().project if session.current() else None)
        if not project:
            raise ValueError("Bind selection rules to a project first.")
        rule = {"schema": "luna.repro.selection.v1", "project_id": project,
                "title": self.title, "description": self.description,
                "auto_publish": auto_publish,
                "items": [{"name": n, "kind": self.candidates[n].kind,
                           "options": self.candidates[n].options, "title": self.candidates[n].title,
                           "description": self.candidates[n].description} for n in self.selected]}
        raw = _json(rule)
        if len(raw) > 65536:
            raise ValueError("Rule exceeds 64 KiB.")
        for secret in (session.current().token if session.current() else None, os.environ.get("LUNA_REPRO_TOKEN")):
            if secret and secret.encode() in raw:
                raise ValueError("A credential appears in selection rule metadata.")
        return _atomic_write(path, raw)

    def show(self):
        """Notebook checkboxes when available; safe metadata console fallback."""
        shell = sys.modules.get("IPython")
        active = vars(shell).get("get_ipython")() if shell else None
        if active is None or active.__class__.__name__ == "TerminalInteractiveShell":
            for row in self.summary():
                print(("[x] " if row["name"] in self.selected else "[ ] ") + row["name"] + " · " + row["reason"])
            print("Local only / 로컬 후보입니다. choose(...), option(...), preview('preview.html'), publish().")
            return self
        try:
            import ipywidgets as widgets
            from IPython.display import display, HTML
        except ImportError:
            print("Optional ipywidgets is unavailable. Use choose(), preview(path), then publish().")
            return self
        heading = widgets.Text(value=self.title, description="Title / 제목")
        description = widgets.Textarea(value=self.description, description="Description")
        checks, titles, descriptions, positions, settings, rows = {}, {}, {}, {}, {}, []
        for index, item in enumerate(self.candidates.values()):
            checks[item.name] = widgets.Checkbox(value=item.name in self.selected, description=item.name, indent=False)
            titles[item.name] = widgets.Text(value=item.title, description="Title")
            descriptions[item.name] = widgets.Text(value=item.description, description="Note")
            positions[item.name] = widgets.BoundedIntText(value=index + 1, min=1, max=MAX_CANDIDATES, description="Order")
            settings[item.name] = widgets.Text(value=json.dumps(item.options), description="Options JSON", placeholder='{"rows": 100, "index": true}')
            more = widgets.Accordion(children=[widgets.VBox([titles[item.name], descriptions[item.name], positions[item.name], settings[item.name]])])
            more.set_title(0, "Title · order · conversion / 제목·순서·변환")
            more.selected_index = None
            rows.append(widgets.VBox([checks[item.name], widgets.HTML(html.escape(item.reason)), more]))
        review = widgets.Button(description="Preview / 미리보기", button_style="info")
        send = widgets.Button(description="Send reviewed / 검토한 결과 전송", button_style="success", disabled=True)
        output = widgets.Output()
        def changed(change):
            send.disabled = True
        for control in [heading, description, *checks.values(), *titles.values(), *descriptions.values(), *positions.values(), *settings.values()]:
            control.observe(changed, names="value")
        def review_clicked(button):
            with output:
                output.clear_output()
                try:
                    names = sorted((n for n in checks if checks[n].value), key=lambda n: positions[n].value)
                    self.choose(*names).edit(title=heading.value, description=description.value)
                    for name in names:
                        options = json.loads(settings[name].value)
                        if type(options) is not dict:
                            raise ValueError
                        self.candidates[name].options = {}
                        self.option(name, title=titles[name].value, description=descriptions[name].value, **options)
                    document = html.escape(self.preview(), quote=True)
                    display(HTML('<iframe sandbox="" title="Selected result preview" style="width:100%;height:600px;border:1px solid #ccd" srcdoc="' + document + '"></iframe>'))
                    send.disabled = False
                except (ValueError, TypeError, OSError):
                    print("Review failed. Check selected type, size, conversion options and project. / 선택·크기·변환·프로젝트를 확인하세요.")
        def send_clicked(button):
            if send.disabled or self._frozen is None:
                return
            send.disabled = True
            with output:
                try:
                    result = self.publish()
                    print(json.dumps(result, ensure_ascii=False))
                except (ValueError, OSError, PublishError):
                    print("Not published. Review project access and the local bundle. / 게시되지 않았습니다. 권한과 로컬 묶음을 확인하세요.")
        review.on_click(review_clicked)
        send.on_click(send_clicked)
        self._widget = widgets.VBox([widgets.HTML("<b>Local candidates / 로컬 후보</b><p>Nothing is sent until Send. Check failures and warnings too. / 전송 버튼을 누르기 전에는 전송하지 않습니다. 실패·경고도 검토하세요.</p>"), heading, description, *rows, widgets.HBox([review, send]), output])
        display(self._widget)
        return self


def _preview(bundle):
    escape = lambda value: html.escape(str(value))
    artifacts = {item["sha256"]: item for item in bundle["artifacts"]}
    body = ["<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; img-src data:; style-src 'unsafe-inline'\">",
            "<style>body{font:16px system-ui;max-width:1000px;margin:24px auto;padding:0 16px;color:#24324a;background:#f5f7fb}section{background:white;padding:20px;margin:14px 0;border:1px solid #dce3ef;border-radius:14px;overflow:auto}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:7px}img{max-width:100%;height:auto}p{white-space:pre-wrap;overflow-wrap:anywhere}</style></head><body>",
            "<h1>" + escape(bundle["title"]) + "</h1><p>Local preview · 로컬 미리보기. No upload / 전송 전</p>",
            "<p>Project / 프로젝트: " + escape(bundle["project_id"]) + "</p><p>" + escape(bundle["description"]) + "</p>"]
    for section in bundle["sections"]:
        body.append("<section><h2>" + escape(section["title"]) + "</h2><p>" + escape(section["description"]) + "</p>")
        for block in section["blocks"]:
            if block["kind"] == "text":
                body.append("<p>" + escape(block["text"]) + "</p>")
            elif block["kind"] == "metrics":
                body.append("<table>" + "".join("<tr><th>" + escape(k) + "</th><td>" + escape(v) + "</td></tr>" for k, v in block["values"].items()) + "</table>")
            elif block["kind"] == "table":
                body.append("<table><tr>" + "".join("<th>" + escape(c) + "</th>" for c in block["columns"]) + "</tr>" + "".join("<tr>" + "".join("<td>" + escape(v) + "</td>" for v in row) + "</tr>" for row in block["rows"]) + "</table>")
            elif block["kind"] == "image":
                item = artifacts[block["sha256"]]
                body.append('<img alt="' + escape(block["caption"]) + '" src="data:' + item["mime"] + ';base64,' + item["data_base64"] + '"><p>' + escape(block["caption"]) + '</p>')
        body.append("<details><summary>Registration/source metadata / 등록·출처</summary><pre>" + escape(json.dumps(section["source"], ensure_ascii=False, indent=2)) + "</pre></details></section>")
    return "".join(body) + "</body></html>"


def _apply_rule(selection, path, auto):
    with Path(path).open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("Rule exceeds 64 KiB.")
    rule = json.loads(raw)
    if (type(rule) is not dict or set(rule) != {"schema", "project_id", "title", "description", "auto_publish", "items"}
            or rule["schema"] != "luna.repro.selection.v1" or type(rule["auto_publish"]) is not bool
            or type(rule["items"]) is not list or not 1 <= len(rule["items"]) <= MAX_CANDIDATES):
        raise ValueError("Invalid selection rule.")
    if not selection.project or rule["project_id"] != selection.project:
        raise ValueError("Rule project does not match the configured project.")
    names = []
    for item in rule["items"]:
        if type(item) is not dict or set(item) != {"name", "kind", "options", "title", "description"}:
            raise ValueError("Invalid rule item.")
        name = item["name"]
        if type(name) is not str or name not in selection.candidates or selection.candidates[name].kind != item["kind"]:
            raise ValueError("A saved candidate is missing or changed type; review the rule explicitly.")
        if type(item["options"]) is not dict:
            raise ValueError("Invalid rule conversion options.")
        names.append(name)
        selection.option(name, title=item["title"], description=item["description"], **item["options"])
    selection.choose(*names).edit(title=rule["title"], description=rule["description"])
    if auto:
        if not rule["auto_publish"]:
            raise ValueError("Automatic send requires both saved auto_publish=True and this call's auto=True.")
        selection._last_receipt = selection.publish()


def select(*objects, namespace=None, title="Research results", description="", project=None, purpose="", sources=None, show=True, rule=None, auto=False):
    """Discover bounded supported objects locally; never traverse objects or directories.

    purpose is a local name-match ranking hint, not an AI request or quality verdict.
    Saved rules require both opt-ins to send automatically, once per invocation.
    """
    if objects and namespace is not None:
        raise ValueError("Pass explicit objects OR namespace={name: value}.")
    if type(auto) is not bool or (auto and rule is None):
        raise ValueError("Automatic send requires an explicitly saved rule.")
    if sources is not None and type(sources) is not dict:
        raise ValueError("sources must map candidate names to explicit source metadata.")
    _text(purpose, 1000)
    frame = inspect.currentframe().f_back
    try:
        registration = _registration(frame)
        if objects:
            if len(objects) > MAX_CANDIDATES:
                raise ValueError("Select at most 100 objects.")
            values = {f"result_{i + 1}": value for i, value in enumerate(objects)}
        else:
            values = namespace if namespace is not None else frame.f_locals
            if type(values) is not dict:
                raise ValueError("namespace must be a plain dictionary.")
            if len(values) > MAX_NAMESPACE:
                raise ValueError("Scope exceeds 1000 names; provide a smaller explicit namespace.")
        found, identities = [], set()
        for name, value in values.items():
            if not adapters.safe_name(name):
                continue
            identity = id(value)
            if not objects and identity in identities and type(value) not in {int, float, bool}:
                continue
            item = _candidate(name, value, (sources or {}).get(name, registration), explicit=bool(objects))
            if item is None:
                continue
            identities.add(identity)
            if purpose:
                terms = re.findall(r"[\w]+", purpose.casefold())
                labels = [name]
                if item.kind == "dataframe":
                    labels.extend(c for c in list(value.columns[:100]) if type(c) is str and adapters.safe_name(c))
                if item.kind == "metrics":
                    labels.extend(value)
                matched = [term for term in terms if any(term in label.casefold() for label in labels)]
                if matched:
                    item.summary["purpose_matches"] = matched
                    item.reason += " · purpose/name match / 목적·이름 일치"
            found.append(item)
            if len(found) > MAX_CANDIDATES:
                raise ValueError("More than 100 candidates; provide a smaller namespace.")
    finally:
        del frame
    if objects and len(found) != len(objects):
        raise ValueError("An explicitly supplied object is unsupported. Use a supported object or existing Page API.")
    if purpose:
        found.sort(key=lambda item: -len(item.summary.get("purpose_matches", [])))
    selection = Selection(found, project=project, title=title, description=description, purpose=purpose)
    if rule is not None:
        _apply_rule(selection, rule, auto)
    if show and not auto:
        selection.show()
    return selection


def publish(*objects, title="Research results", project=None, strict=False, timeout=30, **kwargs):
    """Explicit publication facade; existing Page instances retain their identities."""
    if len(objects) == 1 and type(objects[0]) is Page:
        page = objects[0]
        configured = session.current()
        if project is not None and str(UUID(str(project))) != page.project_id:
            raise ValueError("Page project cannot be rewritten during publication.")
        if configured and configured.project != page.project_id:
            raise ValueError("Configured project does not match this Page.")
        if kwargs:
            raise ValueError("Edit the Page directly before publishing it.")
        return page.publish(endpoint=configured.endpoint if configured else None,
                            token=configured.token if configured else None, strict=strict, timeout=timeout)
    if not objects:
        raise ValueError("publish() requires explicit objects. Use select() to discover candidates first.")
    if "sources" not in kwargs:
        frame = inspect.currentframe().f_back
        try:
            kwargs["sources"] = {f"result_{i + 1}": _registration(frame) for i in range(len(objects))}
        finally:
            del frame
    selection = select(*objects, title=title, project=project, show=False, **kwargs)
    selection.choose(*selection.candidates)
    return selection.publish(strict=strict, timeout=timeout)
