import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from server.cache import connect
from server.duplicates import Duplicates, move_to_trash
from server.library import Library
from server.semantic import Encoder


@unittest.skipIf(os.name == 'nt', 'macOS Trash review uses POSIX descriptor/path file identity; native Trash is unavailable on Windows.')
class DuplicateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.folder = self.home / 'photos'
        self.folder.mkdir()
        Image.new('RGB', (32, 24), 'blue').save(self.folder / 'a.png')
        for name in ('b.png', 'c.png'):
            (self.folder / name).write_bytes((self.folder / 'a.png').read_bytes())
        Image.new('RGB', (64, 48), 'red').save(self.folder / 'other.png')
        self.library = Library(self.folder, self.home / 'cache', Encoder(self.home / 'models'))
        self.addCleanup(self.library.close)
        self.library.scan()
        self.review = self.library.duplicates
        self.image_id = hashlib.sha256((self.folder / 'a.png').read_bytes()).hexdigest()
        self.support = patch('server.duplicates.trash_available', return_value=True)
        self.support.start()
        self.addCleanup(self.support.stop)
        self.fake_trash = self.home / 'simulated-trash'
        self.fake_trash.mkdir()

    def plan(self, paths=None):
        return self.review.plan({'kind': 'exact', 'group': self.image_id, 'paths': paths or ['b.png']})

    def test_selected_original_can_be_trashed_without_a_duplicate_keeper(self):
        plan = self.review.plan_files({'paths': ['other.png']})
        with patch('server.duplicates.move_to_trash', self.fake_move):
            result = self.review.execute({'token': plan['token'], 'confirmed': True})
        self.assertEqual(result['moved'], 1)
        self.assertFalse((self.folder / 'other.png').exists())
        self.assertTrue((self.folder / 'a.png').exists())

    def test_whole_folder_review_lists_every_original_and_is_read_only_until_confirmation(self):
        plan = self.review.plan_files({'folder': ''})
        self.assertEqual({file['path'] for file in plan['files']}, {'a.png', 'b.png', 'c.png', 'other.png'})
        with self.assertRaises(ValueError):
            self.review.execute({'token': plan['token'], 'confirmed': False})
        self.assertEqual(len(list(self.folder.iterdir())), 4)
        with patch('server.duplicates.move_to_trash', self.fake_move):
            result = self.review.execute({'token': plan['token'], 'confirmed': True})
        self.assertEqual(result['moved'], 4)
        self.assertTrue(self.folder.is_dir())
        self.assertEqual(self.library.pictures({})['total'], 0)

    def test_selected_file_review_rejects_invalid_or_changed_selection(self):
        for values in ({'paths': ['missing.png']}, {'paths': ['a.png', 'a.png']}, {'folder': '', 'paths': ['a.png']}, {'paths': '../a.png'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.review.plan_files(values)
        plan = self.review.plan_files({'paths': ['other.png']})
        (self.folder / 'other.png').write_bytes(b'changed')
        with patch('server.duplicates.move_to_trash') as move, self.assertRaises(ValueError):
            self.review.execute({'token': plan['token'], 'confirmed': True})
        move.assert_not_called()

    def fake_move(self, path):
        destination = self.fake_trash / path.name
        path.rename(destination)
        return str(destination)

    def test_exact_and_similar_groups_are_distinct_and_report_logical_size(self):
        exact = self.review.list({})
        self.assertEqual(exact['total'], 1)
        self.assertEqual(exact['items'][0]['kind'], 'exact')
        files = exact['items'][0]['images'][0]['files']
        self.assertEqual([file['path'] for file in files], ['a.png', 'b.png', 'c.png'])
        self.assertEqual(exact['items'][0]['extraBytes'], 2 * (self.folder / 'a.png').stat().st_size)
        self.assertEqual(self.review.list({'kind': 'similar'})['total'], 0)
        with connect(self.library.directory) as db:
            ids = [row[0] for row in db.execute('SELECT id FROM images')]
            db.executemany('INSERT INTO image_groups VALUES (?,?,?)', [(image_id, ids[0], number) for number, image_id in enumerate(ids)])
        similar = self.review.list({'kind': 'similar'})
        self.assertEqual(similar['total'], 1)
        self.assertEqual(len(similar['items'][0]['images']), 2)
        self.assertEqual(sum(len(image['files']) for image in similar['items'][0]['images']), 4)
        self.assertEqual(self.review.list({})['total'], 1)

    def test_plan_is_read_only_and_requires_a_remaining_keeper(self):
        before = {path: path.read_bytes() for path in self.folder.iterdir()}
        plan = self.plan(['b.png', 'c.png'])
        self.assertEqual([file['path'] for file in plan['kept']], ['a.png'])
        self.assertEqual(plan['bytes'], 2 * len(before[self.folder / 'a.png']))
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        for paths in ([], ['a.png', 'b.png', 'c.png'], ['../a.png'], ['b.png', 'b.png'], ['other.png']):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                self.review.plan({'kind': 'exact', 'group': self.image_id, 'paths': paths})

    def test_requires_explicit_confirmation_and_rejects_foreign_tokens(self):
        plan = self.plan()
        with patch('server.duplicates.move_to_trash') as move:
            for values in ({'token': plan['token']}, {'token': plan['token'], 'confirmed': 'true'}, {'confirmed': True}, {'token': 'other', 'confirmed': True}):
                with self.subTest(values=values), self.assertRaises(ValueError):
                    self.review.execute(values)
            move.assert_not_called()

    def test_confirmed_move_updates_catalog_and_repeat_is_idempotent(self):
        plan = self.plan(['b.png', 'c.png'])
        values = {'token': plan['token'], 'confirmed': True}
        with patch('server.duplicates.move_to_trash', side_effect=self.fake_move) as move:
            result = self.review.execute(values)
            repeated = self.review.execute(values)
        self.assertEqual(result, repeated)
        self.assertEqual(move.call_count, 2)
        self.assertEqual(result['state'], 'complete')
        self.assertEqual(result['moved'], 2)
        self.assertTrue((self.folder / 'a.png').is_file())
        self.assertTrue((self.fake_trash / 'b.png').is_file())
        self.assertEqual(self.library.status()['counts']['files'], 2)
        self.assertEqual(self.review.list({})['total'], 0)
        self.assertIn('Put Back', self.review.history()[0]['recovery'])
        self.assertEqual(self.review.history()[0], result)

    def test_changed_selected_file_and_changed_keeper_abort_before_any_move(self):
        for target in ('a.png', 'b.png'):
            original = (self.folder / target).read_bytes()
            plan = self.plan()
            (self.folder / target).write_bytes(b'changed')
            with patch('server.duplicates.move_to_trash') as move, self.assertRaises(ValueError):
                self.review.execute({'token': plan['token'], 'confirmed': True})
            move.assert_not_called()
            (self.folder / target).write_bytes(original)

    def test_expired_review_aborts(self):
        plan = self.plan()
        with connect(self.library.directory) as db:
            db.execute('UPDATE duplicate_reviews SET created=0 WHERE token=?', (plan['token'],))
        with patch('server.duplicates.move_to_trash') as move, self.assertRaisesRegex(ValueError, 'expired'):
            self.review.execute({'token': plan['token'], 'confirmed': True})
        move.assert_not_called()

    def test_partial_failure_is_journaled_and_never_automatically_retried(self):
        plan = self.plan(['b.png', 'c.png'])
        calls = []

        def fail_second(path):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('drive unavailable')
            return self.fake_move(path)

        values = {'token': plan['token'], 'confirmed': True}
        with patch('server.duplicates.move_to_trash', side_effect=fail_second) as move:
            result = self.review.execute(values)
            self.assertEqual(self.review.execute(values), result)
        self.assertEqual(move.call_count, 2)
        self.assertEqual(result['state'], 'partial')
        self.assertEqual(result['moved'], 1)
        self.assertEqual(result['files'][1]['state'], 'failed')
        self.assertTrue((self.folder / 'c.png').is_file())
        self.assertEqual(self.library.status()['counts']['files'], 3)

    def test_interrupted_move_is_preserved_across_reopening_without_replay(self):
        plan = self.plan()
        original_save = self.review._save

        def crash_after_move(token, state, payload, removed=None):
            if removed:
                raise sqlite3.OperationalError('journal disk unavailable')
            return original_save(token, state, payload, removed)

        values = {'token': plan['token'], 'confirmed': True}
        with patch.object(self.review, '_save', side_effect=crash_after_move), patch('server.duplicates.move_to_trash', side_effect=self.fake_move):
            with self.assertRaisesRegex(RuntimeError, 'may have reached Trash'):
                self.review.execute(values)
        reopened = Duplicates(self.library)
        with patch('server.duplicates.move_to_trash') as move:
            result = reopened.execute(values)
        move.assert_not_called()
        self.assertEqual(result['state'], 'executing')
        self.assertEqual(result['files'][0]['state'], 'moving')
        self.assertEqual(reopened.history()[0], result)
        self.assertTrue((self.fake_trash / 'b.png').is_file())

    def test_keeper_removed_during_a_batch_stops_remaining_moves(self):
        plan = self.plan(['b.png', 'c.png'])

        def change_keeper(path):
            destination = self.fake_move(path)
            (self.folder / 'a.png').rename(self.home / 'externally-moved-keeper.png')
            return destination

        with patch('server.duplicates.move_to_trash', side_effect=change_keeper) as move:
            result = self.review.execute({'token': plan['token'], 'confirmed': True})
        self.assertEqual(move.call_count, 1)
        self.assertEqual(result['state'], 'partial')
        self.assertTrue((self.folder / 'c.png').is_file())

    def test_photos_other_platforms_and_closed_libraries_are_read_only(self):
        with patch('server.duplicates.trash_available', return_value=False), self.assertRaises(ValueError):
            self.plan()
        self.library.photos = True
        with self.assertRaises(ValueError):
            self.plan()
        self.library.photos = False
        self.library.close()
        with self.assertRaises(ValueError):
            self.plan()

    def test_symlinks_are_rejected(self):
        path = self.folder / 'b.png'
        path.rename(self.home / 'outside.png')
        try:
            path.symlink_to(self.home / 'outside.png')
        except OSError:
            self.skipTest('Symlinks unavailable')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            self.plan()

    def test_combined_workspace_moves_only_the_selected_source_copy(self):
        secondary = self.home / 'secondary'
        secondary.mkdir()
        (secondary / 'copy.png').write_bytes((self.folder / 'a.png').read_bytes())
        library = Library(self.folder, self.home / 'combined', self.library.semantic.encoder, roots=[self.folder, secondary])
        self.addCleanup(library.close)
        library.scan()
        plan = library.duplicates.plan({'kind': 'exact', 'group': self.image_id, 'paths': ['secondary/copy.png']})
        with patch('server.duplicates.move_to_trash', side_effect=self.fake_move):
            result = library.duplicates.execute({'token': plan['token'], 'confirmed': True})
        self.assertEqual(result['moved'], 1)
        self.assertTrue((self.folder / 'a.png').is_file())
        self.assertTrue((self.folder / 'b.png').is_file())
        self.assertFalse((secondary / 'copy.png').exists())
        self.assertTrue((self.fake_trash / 'copy.png').is_file())

    def test_hard_linked_files_are_read_only(self):
        try:
            os.link(self.folder / 'a.png', self.home / 'linked-copy.png')
        except OSError:
            self.skipTest('Hard links unavailable')
        with self.assertRaisesRegex(ValueError, 'independently stored'):
            self.plan()

    def test_journal_failure_before_move_keeps_originals(self):
        plan = self.plan()
        with patch.object(self.review, '_save', side_effect=OSError('disk full')), patch('server.duplicates.move_to_trash') as move:
            with self.assertRaises(OSError):
                self.review.execute({'token': plan['token'], 'confirmed': True})
        move.assert_not_called()
        self.assertTrue((self.folder / 'b.png').is_file())

    def test_native_trash_bridge_uses_resulting_location_and_reports_failure(self):
        destination = Mock()
        destination.path.return_value = '/simulated-trash/b.png'
        manager = Mock()
        manager.trashItemAtURL_resultingItemURL_error_.return_value = (True, destination, None)
        foundation = Mock()
        foundation.NSFileManager.defaultManager.return_value = manager
        import contextlib
        objc = Mock()
        objc.autorelease_pool.side_effect = contextlib.nullcontext
        with patch.dict('sys.modules', {'Foundation': foundation, 'objc': objc}):
            self.assertEqual(move_to_trash(self.folder / 'b.png'), '/simulated-trash/b.png')
            manager.trashItemAtURL_resultingItemURL_error_.return_value = (False, None, None)
            with self.assertRaises(OSError):
                move_to_trash(self.folder / 'b.png')
        self.assertTrue((self.folder / 'b.png').is_file())
