"""Explicit source selection; temporary synthetic files, no external services."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import luna_repro as repro
from luna_repro import source
from luna_repro.client import _checked_bundle, _source


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.script = self.root / 'compute.py'
        self.script.write_text('secret_outside_selection = "synthetic-only"\ndef calculate():\n    return 2 + 3\n', encoding='utf-8')
        self.git = patch.object(source, '_git', return_value=None)
        self.git.start()
        self.addCleanup(self.git.stop)

    def test_default_has_metadata_without_source_text(self):
        result = source.file(self.script, root=self.root, line_start=2, line_end=3)
        self.assertNotIn('snapshot', result['provenance'])
        self.assertNotIn('synthetic-only', json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertEqual(result['file'], 'compute.py')
        self.assertIsNone(result['provenance']['commit_match'])

    def test_selected_lines_and_hash_match_actual_file(self):
        result = source.file(self.script, root=self.root, line_start=2, line_end=3, snapshot=True)
        snapshot = result['provenance']['snapshot']
        self.assertEqual(snapshot['text'], ''.join(self.script.read_bytes().decode().splitlines(keepends=True)[1:3]))
        self.assertEqual(snapshot['start_line'], 2)
        self.assertEqual(snapshot['sha256'], hashlib.sha256(snapshot['text'].encode()).hexdigest())
        self.assertNotIn('synthetic-only', json.dumps(result))

    def test_rejects_nonexistent_range_and_outside_root(self):
        for start, end in ((0, 1), (3, 2), (1, 4), (True, 2)):
            with self.assertRaises(ValueError):
                source.file(self.script, root=self.root, line_start=start, line_end=end)
        child = self.root / 'allowed'; child.mkdir()
        with self.assertRaises(ValueError):
            source.file(self.script, root=child)
        with self.assertRaises(ValueError):
            source.file(self.root, root=self.root)

    def test_snapshot_is_bounded_and_checksum_checked(self):
        result = source.file(self.script, root=self.root, snapshot=True)
        changed = copy.deepcopy(result)
        changed['provenance']['snapshot']['text'] += '# changed'
        with self.assertRaises(ValueError): _source(changed)
        for text in ('a' * 32769, 'a\n' * 1001):
            self.script.write_text(text, encoding='utf-8')
            with self.assertRaises(ValueError): source.file(self.script, root=self.root, snapshot=True)

    def test_read_limit_applies_if_selected_file_grows_after_stat(self):
        stream = io.BytesIO(b'x' * (source.MAX_SOURCE_BYTES + 100))
        with patch.object(Path, 'open', return_value=stream):
            with self.assertRaisesRegex(ValueError, 'exceeds 1 MiB'):
                source.file(self.script, root=self.root)

    def test_per_page_snapshot_limit_counts_duplicate_source_copies(self):
        self.script.write_text('a' * 32768, encoding='utf-8')
        selected = source.file(self.script, root=self.root, snapshot=True)
        page = repro.page('12345678-1234-5678-1234-567812345678', 'Synthetic', source=selected)
        for number in range(7): page.section('s' + str(number), 'Section').text('Data')
        _checked_bundle(page.bundle())  # page + seven section copies = exactly 256 KiB
        page.section('s8', 'Section').text('Data')
        with self.assertRaises(ValueError): page.bundle()

    def test_function_definition_is_distinct_from_registration(self):
        spec = importlib.util.spec_from_file_location('synthetic_selected_source', self.script)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        selected = source.function(module.calculate, root=self.root, snapshot=True)
        self.assertEqual((selected['line_start'], selected['line_end']), (2, 3))
        self.assertEqual(selected['provenance']['role'], 'definition')
        here = source.registration(root=Path(__file__).parent)
        self.assertEqual(here['provenance']['role'], 'registration')
        self.assertNotIn('snapshot', here['provenance'])

    def test_clean_commit_url_and_dirty_source_no_false_pin(self):
        raw = self.script.read_bytes()
        head = 'a' * 40
        def git(root, args):
            if args == ['rev-parse', '--show-toplevel']: return str(self.root).encode()
            if args == ['rev-parse', 'HEAD']: return head.encode()
            if args[0] == 'cat-file': return str(len(raw)).encode()
            if args[0] == 'show': return raw
        with patch.object(source, '_git', side_effect=git):
            result = source.file(self.script, root=self.root, repository_url='https://github.com/example/repo.git', line_start=2, line_end=3)
            self.assertEqual(result['url'], f'https://github.com/example/repo/blob/{head}/compute.py#L2-L3')
            self.assertTrue(result['provenance']['commit_match'])
            self.script.write_text('changed = True\n', encoding='utf-8')
            result = source.file(self.script, root=self.root, repository_url='https://github.com/example/repo')
            self.assertTrue(result['provenance']['dirty'])
            self.assertNotIn('url', result)

    def notebook(self):
        path = self.root / 'example.ipynb'
        path.write_text(json.dumps({'cells': [{'cell_type': 'code', 'id': 'nbformat-real', 'metadata': {'id': 'colab-real'},
                                                'source': ['value = 2 + 3\n'], 'outputs': [{'data': 'private-output-not-selected'}]}]}), encoding='utf-8')
        return path

    def test_notebook_real_namespaces_and_no_outputs(self):
        path = self.notebook()
        for provider, identity in (('jupyter', 'nbformat-real'), ('colab', 'colab-real')):
            value = source.notebook(path, identity, root=self.root, provider=provider, snapshot=True, role='reference')
            self.assertEqual(value['provenance']['snapshot']['text'], 'value = 2 + 3\n')
            self.assertEqual(value['provenance']['role'], 'reference')
            self.assertNotIn('private-output-not-selected', json.dumps(value))
        with self.assertRaises(ValueError): source.notebook(path, 'nbformat-real', root=self.root, provider='colab')
        with self.assertRaises(ValueError): source.notebook(path, 'colab-real', root=self.root)

    def test_colab_link_uses_observed_provider_cell_id(self):
        result = source.notebook(self.notebook(), 'colab-real', root=self.root, provider='colab',
                                 notebook_url='https://colab.research.google.com/drive/example')
        self.assertEqual(result['url'], 'https://colab.research.google.com/drive/example#scrollTo=colab-real')
        for url in ('https://example.com/notebook', 'https://colab.research.google.com/drive/example?key=secret', 'https://colab.research.google.com/drive/example#scrollTo=wrong'):
            with self.assertRaises(ValueError):
                source.notebook(self.notebook(), 'colab-real', root=self.root, provider='colab', notebook_url=url)

    def test_duplicate_cell_id_and_cell_hash_mismatch_are_refused(self):
        path = self.notebook()
        data = json.loads(path.read_text())
        value = source.notebook(path, 'nbformat-real', root=self.root, snapshot=True)
        value['provenance']['cell_sha256'] = 'f' * 64
        with self.assertRaises(ValueError): _source(value)
        data['cells'] *= 2; path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(ValueError): source.notebook(path, 'nbformat-real', root=self.root)

    def test_notebook_rejects_ambiguous_json_and_reports_invalid_encoding_or_depth(self):
        path = self.notebook()
        for raw in (b'{"cells": [], "cells": []}', b'\xff', b'[' * 2000 + b']' * 2000):
            path.write_bytes(raw)
            with self.assertRaises(ValueError): source.notebook(path, 'nbformat-real', root=self.root)

    def test_helpers_do_not_fetch_or_execute_selected_text(self):
        self.script.write_text('raise RuntimeError("Must never run")\n', encoding='utf-8')
        with patch('socket.create_connection', side_effect=AssertionError('No network')):
            result = source.file(self.script, root=self.root, snapshot=True)
        self.assertIn('Must never run', result['provenance']['snapshot']['text'])


if __name__ == '__main__':
    unittest.main()
