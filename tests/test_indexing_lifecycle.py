"""Exercise pause, shutdown and resume across real processes with deterministic offline vectors."""
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
# Small batches and a bounded delay make the mid-index pause deterministic. Real ONNX
# inference is covered separately by the offline benchmark, not simulated here.
CHILD = '''
import os, time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from server import api, semantic

def load(self):
    self._vision = SimpleNamespace(get_providers=lambda: ['CPUExecutionProvider'])

def features(self, *, images=None, text=None):
    count = len(images) if images is not None else len(text)
    if images is not None:
        with Path(os.environ['ORCHARD_BATCH_AUDIT']).open('a') as output:
            output.write(str(count) + '\\n')
        time.sleep(.25)
    return np.tile(np.array([1., 0.], dtype=np.float32), (count, 1))

semantic.BATCH_SIZE = 4
semantic.Encoder.load = load
semantic.Encoder.features = features
semantic.Encoder.downloaded = lambda self: True
semantic.Encoder.warm = lambda self: None
api.main()
'''


@unittest.skipIf(sys.platform == 'win32', 'POSIX signal shutdown is tested here')
class IndexingLifecycleTests(unittest.TestCase):
    def test_pause_quit_restart_resume_preserves_completed_batches(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            photos, data = root / 'photos', root / 'data'
            photos.mkdir()
            data.mkdir()
            for number in range(40):
                with Image.new('RGB', (32, 32), (number * 5, 20, 200)) as image:
                    image.save(photos / f'{number:02}.png')
            originals = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in photos.iterdir()}
            (data / 'indexing.json').write_text(json.dumps({'paused': True, 'threads': 2}))
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            url = f'http://127.0.0.1:{port}'
            audit, log = root / 'batches.txt', root / 'server.log'

            def call(route, payload=None):
                body = None if payload is None else json.dumps(payload).encode()
                request = urllib.request.Request(url + route, body, {'Content-Type': 'application/json'})
                with urllib.request.urlopen(request, timeout=3) as response:
                    return json.load(response)

            def wait(process, predicate):
                deadline = time.monotonic() + 120
                last = None
                while time.monotonic() < deadline:
                    self.assertIsNone(process.poll(), log.read_text()[-6000:])
                    try:
                        last = call('/api/status')['library']
                        if last and predicate(last):
                            return last
                    except OSError:
                        pass
                    time.sleep(.05)
                self.fail(f'Timed out: {last!r}; {log.read_text()[-6000:]}')

            def stop(process):
                if process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                        self.fail('Paused indexing prevented clean shutdown')
                self.assertEqual(process.returncode, 0, log.read_text()[-6000:])

            with log.open('wb') as output:
                def start():
                    return subprocess.Popen([sys.executable, '-c', CHILD, str(photos), '--data-dir', str(data),
                                             '--port', str(port), '--no-watch'], cwd=ROOT,
                                            env={**os.environ, 'HF_HUB_OFFLINE': '1', 'ORCHARD_BATCH_AUDIT': str(audit)},
                                            stdout=output, stderr=subprocess.STDOUT)

                first = start()
                try:
                    initial = wait(first, lambda library: library['updated'] and library['scan']['state'] == 'ready')
                    self.assertEqual(initial['search']['state'], 'paused')
                    self.assertEqual(initial['search']['indexed'], 0)
                    self.assertEqual(call('/api/indexing')['active_threads'], 2)
                    call('/api/indexing', {'paused': False})
                    wait(first, lambda library: library['search']['indexed'] >= 4)
                    call('/api/indexing', {'paused': True})
                    time.sleep(.6)  # Allow the in-flight four-image batch to commit.
                    paused = call('/api/status')['library']['search']['indexed']
                    self.assertGreater(paused, 0)
                    self.assertLess(paused, 40)
                    time.sleep(.3)
                    self.assertEqual(call('/api/status')['library']['search']['indexed'], paused)
                finally:
                    stop(first)
                second = start()
                try:
                    reopened = wait(second, lambda library: library['updated'] and library['scan']['state'] == 'ready')
                    self.assertEqual(reopened['search']['state'], 'paused')
                    self.assertEqual(reopened['search']['indexed'], paused)
                    call('/api/indexing', {'paused': False})
                    finished = wait(second, lambda library: library['search']['state'] == 'ready')
                    self.assertEqual(finished['search']['indexed'], 40)
                finally:
                    stop(second)
            self.assertEqual(sum(map(int, audit.read_text().splitlines())), 40, 'Completed batches must not repeat')
            self.assertEqual(originals, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in photos.iterdir()})
