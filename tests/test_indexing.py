from pathlib import Path
import tempfile
import threading
import unittest

from server.indexing import IndexingControls


class IndexingControlTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'indexing.json'
        self.controls = IndexingControls(self.path)

    def test_pause_and_cpu_setting_survive_restart(self):
        self.controls.update({'paused': True, 'threads': 2})
        reopened = IndexingControls(self.path)
        self.assertEqual(reopened.status(), {'paused': True, 'threads': 2})

    def test_invalid_requests_do_not_change_settings(self):
        for value in ({'paused': 'true'}, {'threads': True}, {'threads': -1}, {'threads': 65}, {'other': 1}, {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.controls.update(value)
        self.assertFalse(self.path.exists())

    def test_corrupt_settings_do_not_prevent_launch(self):
        self.path.write_text('not json')
        self.assertEqual(IndexingControls(self.path).status(), {'paused': False, 'threads': 0})

    def test_pause_blocks_work_until_resume(self):
        self.controls.update({'paused': True})
        completed = threading.Event()
        worker = threading.Thread(target=lambda: (self.controls.checkpoint(lambda: False), completed.set()))
        worker.start()
        try:
            self.assertFalse(completed.wait(.15))
            self.controls.update({'paused': False})
            self.assertTrue(completed.wait(2))
        finally:
            self.controls.update({'paused': False})
            worker.join(2)

    def test_shutdown_interrupts_a_paused_worker(self):
        self.controls.update({'paused': True})
        cancelled = threading.Event()
        result = []
        worker = threading.Thread(target=lambda: result.append(self.controls.checkpoint(cancelled.is_set)))
        worker.start()
        cancelled.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result, [False])
