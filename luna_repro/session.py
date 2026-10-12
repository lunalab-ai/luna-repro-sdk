"""Session-local defaults. Credentials never appear in repr or saved rules."""
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from .client import _url


@dataclass(frozen=True)
class Configuration:
    project: str
    endpoint: str | None = None
    token: str | None = field(default=None, repr=False)
    outbox: str | None = None
    project_title: str = ""
    expires_at: str = ""

    def reusable(self):
        if not self.token or not self.expires_at:
            return False
        try:
            return datetime.fromisoformat(self.expires_at.replace("Z", "+00:00")) > datetime.now(timezone.utc)
        except (TypeError, ValueError):
            return False


_configuration = ContextVar("luna_repro_configuration", default=None)


def configure(project, *, endpoint=None, token=None, outbox=None):
    """Set memory-only defaults for this context; performs no network or disk I/O."""
    if project is None:
        raise ValueError("Choose a project UUID; configure() never creates projects.")
    project = str(UUID(str(project)))
    if endpoint is not None:
        endpoint = _url(endpoint, endpoint=True).rstrip("/")
    if token is not None and (type(token) is not str or not token or any(ord(c) < 33 or ord(c) > 126 for c in token)):
        raise ValueError("Use a session connection key without whitespace.")
    value = Configuration(project, endpoint, token, str(outbox) if outbox is not None else None)
    _configuration.set(value)
    return value


def current():
    return _configuration.get()


def clear():
    """Forget the local credential. Server revocation is a separate platform action."""
    _configuration.set(None)
