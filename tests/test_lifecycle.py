"""Real processes and HTTP, with generated photos and no access to the user's library."""
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


@unittest.skipIf(sys.platform == 'win32', 'SIGTERM lifecycle is POSIX-specific')
class LifecycleTests(unittest.TestCase):
    def test_single_instance_quit_relaunch_preserves_index_and_originals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            photos = root / 'photos'
            photos.mkdir()
            original = photos / 'blue.png'
            Image.new('RGB', (64, 64), 'blue').save(original)
            digest = hashlib.sha256(original.read_bytes()).hexdigest()
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            url = f'http://127.0.0.1:{port}/api/status'
            launcher = os.environ.get('ORCHARD_TEST_LAUNCHER')
            prefix = [str(Path(launcher).resolve()), '--browser'] if launcher else [sys.executable, '-m', 'server.api']
            command = [*prefix, '--port', str(port), '--data-dir', str(root / 'data'), '--no-watch']

            def status():
                with urllib.request.urlopen(url, timeout=1) as response:
                    return json.load(response)

            def ready(process):
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    self.assertIsNone(process.poll(), 'Server exited before becoming ready')
                    try:
                        result = status()
                        if result['library'] and result['library']['scan']['state'] == 'ready':
                            return result
                    except OSError:
                        pass
                    time.sleep(0.1)
                self.fail('Server did not finish scanning')

            def launch(folder=None):
                process = subprocess.Popen(command + ([str(folder)] if folder else []), cwd=ROOT,
                                           env={**os.environ, 'HF_HUB_OFFLINE': '1', 'BROWSER': 'true'}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.addCleanup(lambda: stop(process))
                return process

            def stop(process):
                if process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                        self.fail('Server failed to quit on SIGTERM')

            first = launch(photos)
            before = ready(first)
            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(second.returncode, 0, second.stderr)
            if not launcher:
                self.assertIn('already running', second.stdout)
            self.assertIsNone(first.poll())
            stop(first)
            with self.assertRaises(OSError):
                status()
            again = launch()
            after = ready(again)
            self.assertEqual(after['folder']['id'], before['folder']['id'])
            self.assertEqual(after['library']['counts'], before['library']['counts'])
            self.assertEqual(after['folder']['path'], str(photos))
            stop(again)
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), digest)
