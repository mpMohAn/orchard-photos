from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from server.indexing import IndexingControls, InferenceQueue
from server.library import Library
from server.semantic import Encoder


class InferenceQueueTests(unittest.TestCase):
    def test_exception_releases_the_turn(self):
        queue = InferenceQueue()
        with self.assertRaises(RuntimeError), queue.turn(lambda: False) as active:
            self.assertTrue(active)
            raise RuntimeError('failed inference')
        with queue.turn(lambda: False) as active:
            self.assertTrue(active)

    def test_cancelled_waiter_leaves_the_queue(self):
        queue = InferenceQueue()
        cancel = threading.Event()
        result = []

        def waiter():
            with queue.turn(cancel.is_set) as active:
                result.append(active)

        with queue.turn(lambda: False):
            thread = threading.Thread(target=waiter)
            thread.start()
            cancel.set()
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(result, [False])
        self.assertEqual(queue.waiters, [])


class IndexingFairnessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.photos = self.root / 'photos'
        self.photos.mkdir()
        for number in range(20):
            Image.new('RGB', (32, 32), (number, 50, 100)).save(self.photos / f'{number}.png')
        self.encoder = Encoder(self.root / 'models')
        self.encoder.controls = IndexingControls(self.root / 'indexing.json')
        self.library = Library(self.photos, self.root / 'catalog', self.encoder)
        self.library.scan()
        self.addCleanup(self.library.close)

    @staticmethod
    def wait_for(predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            time.sleep(.01)
        return predicate()

    def fake_face(self, observed):
        class Face:
            def __init__(self, directory):
                pass

            def load(self, cancelled, resource=None):
                return True

            def encode(self, image):
                observed()
                return []
        return Face

    def test_people_progresses_while_visual_indexing_is_paused(self):
        seen = threading.Event()
        self.encoder.controls.update({'paused': True})
        thread = threading.Thread(target=self.library.index)
        with patch.object(self.encoder, 'load'), patch.object(self.encoder, 'features', return_value=np.ones((20, 768), dtype=np.float32)), patch.object(self.library.groups, 'update', return_value=False), patch('server.faces.FaceEncoder', self.fake_face(seen.set)):
            thread.start()
            try:
                self.assertTrue(self.wait_for(self.library.semantic_lock.locked))
                self.library.people.update({'action': 'enable', 'consent': True})
                self.assertTrue(seen.wait(3), 'People was blocked by paused visual indexing')
                self.assertTrue(self.wait_for(lambda: self.library.people.status()['processed'] == 20))
            finally:
                self.library.close()
                thread.join(3)
        self.assertFalse(thread.is_alive())

    def test_people_gets_a_turn_between_visual_batches(self):
        first = threading.Event()
        release = threading.Event()
        events = []

        def features(*, images):
            events.append('visual')
            if len(events) == 1:
                first.set()
                release.wait(3)
            return np.ones((len(images), 768), dtype=np.float32)

        thread = threading.Thread(target=self.library.index)
        with patch.object(self.encoder, 'load'), patch.object(self.encoder, 'features', side_effect=features), patch.object(self.library.groups, 'update', return_value=False), patch('server.faces.FaceEncoder', self.fake_face(lambda: events.append('people'))):
            thread.start()
            try:
                self.assertTrue(first.wait(3))
                self.library.people.update({'action': 'enable', 'consent': True})
                self.assertTrue(self.wait_for(lambda: len(self.library.inference.waiters) > 0))
                release.set()
                thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertEqual(events[0], 'visual')
                self.assertLess(events.index('people'), events.index('visual', 1))
            finally:
                release.set()
                self.library.close()
                thread.join(3)
