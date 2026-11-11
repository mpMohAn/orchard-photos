from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from server.cache import connect
from server.faces import People
from server.library import Library
from server.semantic import Encoder


class PeopleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.photos = self.root / 'photos'
        self.photos.mkdir()
        for index, colour in enumerate(('red', 'blue', 'green')):
            Image.new('RGB', (48, 48), colour).save(self.photos / f'{index}.png')
        self.library = Library(self.photos, self.root / 'catalog', Encoder(self.root / 'models'))
        self.library.scan()
        self.addCleanup(self.library.close)
        self.people = self.library.people
        self.ids = [item['id'] for item in self.library.pictures({})['items']]
        self.vector = np.eye(1, 128, dtype='<f4').reshape(-1)

    def seed(self):
        with connect(self.library.directory) as db:
            People._store(db, self.ids[0], self.vector, [0, 0, 1, 1], b'crop')
            People._store(db, self.ids[1], self.vector, [0, 0, 1, 1], b'crop')
            People._store(db, self.ids[2], np.roll(self.vector, 1), [0, 0, 1, 1], b'crop')

    def test_off_by_default_and_requires_explicit_consent(self):
        self.assertFalse(self.people.status()['enabled'])
        with self.assertRaises(ValueError):
            self.people.update({'action': 'enable'})
        self.assertEqual(self.people.status()['processed'], 0)
        self.assertFalse((self.root / 'models/faces').exists())

    def test_groups_persist_and_names_filter_photos(self):
        self.seed()
        groups = self.people.status()['people']
        self.assertEqual([person['photos'] for person in groups], [2, 1])
        self.people.update({'action': 'name', 'person': groups[0]['id'], 'name': 'Family'})
        self.assertEqual(People(self.library).status()['people'][0]['name'], 'Family')
        self.assertEqual(self.library.pictures({'person': groups[0]['id']})['total'], 2)
        self.assertEqual(self.library.pictures({'q': 'person:"Family"', 'mode': 'hybrid'})['total'], 2)

    def test_manual_merge_separate_and_ignore_leave_originals_intact(self):
        self.seed()
        groups = self.people.status()['people']
        result = self.people.update({'action': 'merge', 'source': groups[1]['id'], 'target': groups[0]['id']})
        self.assertEqual(result['people'][0]['photos'], 3)
        self.assertEqual(self.library.pictures({'person': groups[0]['id']})['total'], 3)
        face = self.people.members(groups[0]['id'])[0]['id']
        self.people.update({'action': 'separate', 'face': face})
        self.assertEqual(len(self.people.status()['people']), 2)
        self.assertEqual(self.library.pictures({'person': groups[0]['id']})['total'], 2)
        self.people.update({'action': 'ignore', 'face': face})
        self.assertIsNone(self.people.crop(face))
        self.assertEqual(len(list(self.photos.glob('*.png'))), 3)

    def test_clear_requires_confirmation_and_erases_face_data(self):
        self.seed()
        with self.assertRaises(ValueError):
            self.people.update({'action': 'clear'})
        self.people.update({'action': 'clear', 'confirmed': True})
        self.assertEqual(self.people.status()['people'], [])
        self.assertFalse(self.people.status()['enabled'])
        self.assertEqual(self.library.pictures({})['total'], 3)

    def test_pause_and_clear_prevent_in_flight_results_from_reappearing(self):
        entered, release = threading.Event(), threading.Event()
        vector = self.vector

        class FakeEncoder:
            def __init__(self, directory):
                pass

            def load(self, cancelled):
                return True

            def encode(self, image):
                entered.set()
                release.wait(3)
                return [(vector, [0, 0, 1, 1], b'crop')]

        with patch('server.faces.FaceEncoder', FakeEncoder):
            self.people.update({'action': 'enable', 'consent': True})
            self.assertTrue(entered.wait(3))
            self.people.update({'action': 'clear', 'confirmed': True})
            release.set()
            deadline = time.monotonic() + 3
            while self.people.worker_lock.locked() and time.monotonic() < deadline:
                time.sleep(.01)
        self.assertFalse(self.people.worker_lock.locked())
        self.assertEqual(self.people.status()['processed'], 0)
        self.assertEqual(self.people.status()['people'], [])

    def test_different_faces_in_the_same_photo_stay_separate(self):
        with connect(self.library.directory) as db:
            People._store(db, self.ids[0], self.vector, [0, 0, .5, 1], b'first')
            People._store(db, self.ids[0], self.vector, [.5, 0, 1, 1], b'second')
        self.assertEqual(len(self.people.status()['people']), 2)

    def test_model_version_change_preserves_groups_until_confirmed_clear(self):
        self.seed()
        with connect(self.library.directory) as db:
            db.execute('UPDATE people_settings SET version=?', ('older-model',))
        people = People(self.library)
        self.assertFalse(people.status()['enabled'])
        self.assertEqual(len(people.status()['people']), 2)
        with self.assertRaises(ValueError):
            people.update({'action': 'enable', 'consent': True})
        people.update({'action': 'clear', 'confirmed': True})
        self.assertTrue(people.compatible)
        self.assertEqual(people.status()['people'], [])
