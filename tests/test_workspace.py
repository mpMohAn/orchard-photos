"""Combined catalogs use generated images and isolated data only."""
import json
from pathlib import Path, PureWindowsPath
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from server.api import App


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.roots = [self.home / 'one' / 'photos', self.home / 'two' / 'photos']
        for number, root in enumerate(self.roots):
            root.mkdir(parents=True)
            Image.new('RGB', (32, 24), (number * 100, 80, 20)).save(root / 'same-name.png')
        (self.roots[1] / 'copy.png').write_bytes((self.roots[0] / 'same-name.png').read_bytes())
        self.app = App(self.home / 'data')
        self.addCleanup(self.app.close)

    def open(self, paths):
        # Suppress only the automatic scan launch, then scan with real executor threads.
        with patch('server.api.threading.Thread'):
            library = self.app.open_many([str(path) for path in paths])
        library.scan()
        self.assertEqual(library.scan_state['state'], 'ready')
        return library

    def test_combined_catalog_deduplicates_and_retains_source_identity(self):
        library = self.open(self.roots)
        rows = library.pictures({})['items']
        self.assertEqual(len(rows), 2)
        self.assertEqual(library.status()['counts']['files'], 3)
        self.assertEqual(library.status()['counts']['duplicates'], 1)
        roots = self.app.status()['folder']['roots']
        self.assertEqual([item['prefix'] for item in roots], ['photos', 'photos (2)'])
        for root in roots:
            filtered = library.pictures({'folder': root['prefix']})
            self.assertEqual(filtered['total'], 1 if root['prefix'] == 'photos' else 2)
        self.assertEqual(library.pictures({'q': 'copy', 'mode': 'name'})['total'], 1)
        for row in rows:
            details = library.details(row['id'])
            for entry in details['files']:
                original = library.original(row['id'], entry['path'])
                self.assertTrue(original.is_file())
                self.assertEqual(str(original), entry['original'])
            self.assertTrue(library.thumbnail(row['id']).is_file())
            self.assertTrue(library.display(row['id']).is_file())
        self.assertEqual(sum(item['count'] for item in library.facets()['folders']), 3)
        self.assertEqual(sum(item['count'] for item in library.timeline({})['months']), 2)

    def test_workspace_reopens_with_same_catalog_and_missing_roots_keep_entries(self):
        library = self.open(self.roots)
        expected = library.directory
        before = library.pictures({})
        self.app.close()
        moved = self.roots[1].with_name('disconnected')
        self.roots[1].rename(moved)
        restored = App(self.home / 'data')
        self.addCleanup(restored.close)
        with patch('server.api.threading.Thread'):
            restored.restore()
        self.assertEqual(restored.current().directory, expected)
        restored.current().scan()
        self.assertEqual(restored.current().scan_state['state'], 'error')
        self.assertEqual(restored.current().pictures({}), before)
        moved.rename(self.roots[1])
        restored.current().scan()
        self.assertEqual(restored.current().scan_state['state'], 'ready')

    def test_invalid_and_overlapping_roots_leave_current_workspace_open(self):
        library = self.open([self.roots[0]])
        for values in (None, [], ['relative'], [4], [str(self.roots[0]), str(self.roots[0].parent)],
                       [str(self.home / 'missing')], [str(self.roots[0])] * 17):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.app.open_many(values)
            self.assertIs(self.app.current(), library)
            self.assertFalse(library.closed.is_set())

    def test_failed_workspace_save_retains_old_catalog_and_saved_paths(self):
        library = self.open([self.roots[0]])
        state = self.app.data_dir / 'workspace.json'
        saved = state.read_bytes()
        original_replace = Path.replace

        def replace(path, destination):
            if Path(destination) == state:
                raise OSError('disk full')
            return original_replace(path, destination)

        with patch.object(Path, 'replace', replace), self.assertRaisesRegex(OSError, 'disk full'):
            self.app.open_many([str(root) for root in self.roots])
        self.assertEqual(state.read_bytes(), saved)
        self.assertIs(self.app.current(), library)
        self.assertFalse(library.closed.is_set())

    def test_root_order_is_stable_and_removing_a_root_keeps_originals(self):
        originals = {path: path.read_bytes() for root in self.roots for path in root.glob('*.png')}
        library = self.open(list(reversed(self.roots)))
        self.assertIs(self.open(self.roots), library)
        self.open([self.roots[1]])
        self.assertTrue(library.closed.is_set())
        self.assertEqual(json.loads((self.app.data_dir / 'workspace.json').read_text()), [str(self.roots[1])])
        self.assertEqual(originals, {path: path.read_bytes() for path in originals})

    def test_source_paths_reject_posix_and_windows_traversal(self):
        library = self.open(self.roots)
        source = library.scanner.source
        prefix = next(iter(source.roots))
        for path in ('/etc/passwd', f'{prefix}/../outside.png', 'unknown/photo.png'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                source.file(path)
        with patch('server.sources.Path', PureWindowsPath):
            for tail in (r'..\outside.png', r'C:\outside.png', r'\outside.png'):
                with self.subTest(tail=tail), self.assertRaises(ValueError):
                    source.file(f'{prefix}/{tail}')

    def test_path_objects_keep_the_single_folder_entry_point(self):
        with patch('server.api.threading.Thread'):
            library = self.app.open(self.roots[0])
        self.assertEqual(library.folder, self.roots[0])

    def test_photos_cannot_be_combined_with_folders(self):
        library = self.open([self.roots[0]])
        fake_photos = self.home / 'system.photoslibrary'
        with patch.object(self.app, 'resolve', side_effect=[self.roots[0], fake_photos]):
            with self.assertRaisesRegex(ValueError, 'Apple Photos separately'):
                self.app.open_many([str(self.roots[0]), str(fake_photos)])
        self.assertIs(self.app.current(), library)
        self.assertFalse(library.closed.is_set())

    def test_sort_orders_are_stable_and_do_not_mutate_cached_tiles(self):
        library = self.open(self.roots)
        newest = library.pictures({})['items']
        for order, key, reverse in (
            ('oldest', lambda row: (row['date'], row['id']), False),
            ('name-asc', lambda row: (Path(row['path']).name.casefold(), row['path'].casefold(), row['id']), False),
            ('name-desc', lambda row: (Path(row['path']).name.casefold(), row['path'].casefold(), row['id']), True),
            ('size-asc', lambda row: (row['size'], row['id']), False),
            ('size-desc', lambda row: (row['size'], row['id']), True),
        ):
            with self.subTest(order=order):
                expected = sorted(newest, key=key, reverse=reverse)
                self.assertEqual(library.pictures({'sort': order})['items'], expected)
                first = library.pictures({'sort': order, 'limit': '1'})
                second = library.pictures({'sort': order, 'limit': '1', 'offset': '1'})
                self.assertEqual(first['items'] + second['items'], expected)
        self.assertEqual(library.pictures({})['items'], newest)
        with self.assertRaisesRegex(ValueError, 'valid image order'):
            library.pictures({'sort': 'DROP TABLE images'})
        with self.assertRaisesRegex(ValueError, 'relevance'):
            library.pictures({'q': 'forest', 'mode': 'visual', 'sort': 'name-asc'})
