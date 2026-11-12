from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from server.library import Library
from server.semantic import Encoder
from server.watcher import FolderChanges


class FolderChangesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.photos = self.root / 'photos'
        self.photos.mkdir()
        self.library = Library(self.photos, self.root / 'data', Encoder(self.root / 'models'))
        self.addCleanup(self.library.close)
        self.library.scan()
        self.changes = FolderChanges()
        self.assertTrue(self.changes.changed(self.library))
        self.assertFalse(self.changes.changed(self.library))

    def settle_and_scan(self):
        self.assertFalse(self.changes.changed(self.library))
        self.assertTrue(self.changes.changed(self.library))
        self.library.scan(retry=True)

    def test_added_image_and_new_subfolder_are_detected(self):
        folder = self.photos / 'new'
        folder.mkdir()
        Image.new('RGB', (32, 32), 'blue').save(folder / 'photo.png')
        self.settle_and_scan()
        self.assertEqual(self.library.pictures({})['total'], 1)
        Image.new('RGB', (32, 32), 'red').save(folder / 'second.png')
        self.settle_and_scan()
        self.assertEqual(self.library.pictures({})['total'], 2)

    def test_download_is_retried_after_incomplete_file_finishes(self):
        path = self.photos / 'download.png'
        path.write_bytes(b'incomplete')
        self.settle_and_scan()
        self.assertEqual(self.library.pictures({})['total'], 0)
        self.assertFalse(self.changes.changed(self.library))
        Image.new('RGB', (32, 32), 'green').save(path)
        self.settle_and_scan()
        self.assertEqual(self.library.pictures({})['total'], 1)

    def test_download_finishing_before_next_probe_is_detected(self):
        path = self.photos / 'download.png'
        path.write_bytes(b'incomplete')
        self.settle_and_scan()
        Image.new('RGB', (32, 32), 'green').save(path)
        self.settle_and_scan()
        self.assertEqual(self.library.pictures({})['total'], 1)

    def test_steady_directory_does_not_request_repeated_scans(self):
        for _ in range(10):
            self.assertFalse(self.changes.changed(self.library))

    def test_continuous_additions_have_a_bounded_debounce(self):
        with patch('server.watcher.time.monotonic', side_effect=[10, 14]):
            (self.photos / 'first.png').write_bytes(b'first')
            self.assertFalse(self.changes.changed(self.library))
            (self.photos / 'second.png').write_bytes(b'second')
            self.assertTrue(self.changes.changed(self.library))

    def test_index_inside_photo_folder_is_excluded(self):
        library = Library(self.photos, self.photos / 'index', Encoder(self.root / 'other-models'))
        self.addCleanup(library.close)
        library.scan()
        changes = FolderChanges()
        self.assertTrue(changes.changed(library))
        self.assertNotIn(library.directory, changes.directories)
        (library.directory / 'internal-file').write_text('index update')
        self.assertFalse(changes.changed(library))

    def test_closed_library_is_skipped(self):
        self.library.close()
        self.assertFalse(self.changes.changed(self.library))
