"""Exercise the generated clone wrapper with a child that cleans up slowly."""
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest


@unittest.skipUnless(sys.platform == 'darwin', 'macOS clone launcher')
class CloneLauncherTests(unittest.TestCase):
    def check_shutdown(self, requested_signal, child_status):
        template = (Path(__file__).resolve().parent.parent / 'scripts/install-app').read_text()
        wrapper = template.split('status=0\n', 1)[1].split('\nSCRIPT', 1)[0]
        wrapper = 'status=0\n' + wrapper.replace('\\$', '$')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            child = root / 'child.py'
            child.write_text(
                'import os, pathlib, signal, time\n'
                'root = pathlib.Path(__file__).parent\n'
                'def stop(*args):\n'
                '    time.sleep(0.25)\n'
                '    (root / "finished").touch()\n'
                f'    raise SystemExit({child_status})\n'
                'signal.signal(signal.SIGTERM, stop)\n'
                '(root / "ready").write_text(str(os.getpid()))\n'
                'while True: time.sleep(0.05)\n')
            orchard = root / 'orchard'
            orchard.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(child))}\n')
            orchard.chmod(0o700)
            process = subprocess.Popen(['/bin/sh', '-c', wrapper], cwd=root,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 5
                while not (root / 'ready').exists() and time.monotonic() < deadline:
                    self.assertIsNone(process.poll())
                    time.sleep(0.01)
                self.assertTrue((root / 'ready').exists(), 'Child failed to start')
                process.send_signal(requested_signal)
                self.assertEqual(process.wait(timeout=5), child_status)
                self.assertTrue((root / 'finished').exists(), 'Wrapper exited before child cleanup')
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                if (root / 'ready').exists() and not (root / 'finished').exists():
                    try:
                        os.kill(int((root / 'ready').read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_sigterm_waits_for_clean_shutdown(self):
        self.check_shutdown(signal.SIGTERM, 0)

    def test_sigint_waits_for_clean_shutdown(self):
        self.check_shutdown(signal.SIGINT, 0)

    def test_real_child_failure_is_preserved(self):
        self.check_shutdown(signal.SIGTERM, 7)
