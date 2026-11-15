"""Unit tests for ss_save: hash semantics, archive validity, save verdicts."""
import os
import sys
import tempfile
import unittest
import zipfile

import _stubs
from _stubs import FakeTime

import ss_save as S


class Sha(unittest.TestCase):
    def test_readable_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            fh.write(b'hello')
            path = fh.name
        try:
            self.assertEqual(len(S.sha(path)), 16)
        finally:
            os.unlink(path)

    def test_missing_is_none(self):
        self.assertIsNone(S.sha(os.path.join(tempfile.gettempdir(), 'no_such_file_xyz.smc2')))


class ArchiveOk(unittest.TestCase):
    def test_valid_zip(self):
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as fh:
            path = fh.name
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('a.xml', b'<data/>')
        try:
            self.assertTrue(S.archive_ok(path))
        finally:
            os.unlink(path)

    def test_not_a_zip(self):
        with tempfile.NamedTemporaryFile(suffix='.smc2', delete=False) as fh:
            fh.write(b'not a zip')
            path = fh.name
        try:
            self.assertFalse(S.archive_ok(path))
        finally:
            os.unlink(path)

    def test_empty_zip(self):
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as fh:
            path = fh.name
        with zipfile.ZipFile(path, 'w'):
            pass
        try:
            self.assertFalse(S.archive_ok(path))
        finally:
            os.unlink(path)

    def test_missing(self):
        self.assertFalse(S.archive_ok(os.path.join(tempfile.gettempdir(), 'no_such_xyz.zip')))


class Classify(unittest.TestCase):
    def test_saved(self):
        self.assertEqual(S.classify_save('aaa', 'bbb', True), 'SAVED')

    def test_unchanged(self):
        self.assertEqual(S.classify_save('aaa', 'aaa', True), 'UNCHANGED')

    def test_missing_is_not_saved(self):
        self.assertEqual(S.classify_save('aaa', None, False), 'MISSING')

    def test_invalid_is_not_saved(self):
        self.assertEqual(S.classify_save('aaa', 'bbb', False), 'INVALID')

    def test_no_baseline(self):
        self.assertEqual(S.classify_save(None, 'bbb', True), 'UNCHANGED')


class ChangedSince(unittest.TestCase):
    def setUp(self):
        self._pop, self._time, self._sha = S.pop_lines, S.time, S.sha
        S.pop_lines = lambda *a, **k: None
        S.time = FakeTime()

    def tearDown(self):
        S.pop_lines, S.time, S.sha = self._pop, self._time, self._sha

    def test_vanished_file_not_a_change(self):
        S.sha = lambda p: None
        lines = []
        ok, _ = S.changed_since('x.smc2', 'old', 1, lines, 'after Ctrl+S')
        self.assertFalse(ok)
        self.assertTrue(any('unreadable' in ln for ln in lines))

    def test_change_detected(self):
        seq = iter(['old', 'new', 'new', 'new'])
        S.sha = lambda p: next(seq)
        ok, secs = S.changed_since('x.smc2', 'old', 1, [], 'after Ctrl+S')
        self.assertTrue(ok)
        self.assertEqual(secs, 3.0)

    def test_missing_then_change(self):
        seq = iter([None, 'new', 'new', 'new'])
        S.sha = lambda p: next(seq)
        ok, _ = S.changed_since('x.smc2', 'old', 1, [], 'after Ctrl+S')
        self.assertTrue(ok)

    def test_unchanged(self):
        S.sha = lambda p: 'old'
        ok, _ = S.changed_since('x.smc2', 'old', 1, [], 'after Ctrl+S')
        self.assertFalse(ok)


class MainAbort(unittest.TestCase):
    def test_unreadable_baseline_aborts_nonzero(self):
        saved = {k: getattr(S.U, k) for k in ('resolve_pid', 'main_window', 'dump')}
        old_sha, old_argv = S.sha, sys.argv
        dumped = []
        S.U.resolve_pid = lambda x: 1
        S.U.main_window = lambda pid: {'title': 't', 'hwnd': 1}
        S.U.dump = lambda path, head, rest: dumped.append(path)
        S.sha = lambda p: None
        with tempfile.TemporaryDirectory() as out:
            sys.argv = ['ss_save.py', '1', '--file', 'missing.smc2', '--out', out]
            try:
                self.assertEqual(S.main(), 1)
            finally:
                sys.argv = old_argv
                S.sha = old_sha
                for k, v in saved.items():
                    setattr(S.U, k, v)
        self.assertEqual(len(dumped), 1)


if __name__ == '__main__':
    unittest.main()