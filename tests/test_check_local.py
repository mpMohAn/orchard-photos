"""Runner tests use only standard library and generated fixtures."""
import contextlib
import io
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
runner = runpy.run_path(str(ROOT / 'scripts/check-local'))


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def invoke(self, args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = runner['main'](args, self.root)
        return code, output.getvalue()

    def test_default_does_not_execute_or_create_files(self):
        with patch('subprocess.Popen', side_effect=AssertionError('must not execute')):
            code, output = self.invoke([])
        self.assertEqual(code, 0)
        self.assertIn('Plan only', output)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_missing_environment_is_skipped(self):
        code, output = self.invoke(['--run'])
        self.assertEqual(code, 0)
        self.assertIn('SKIPPED', output)
        self.assertIn('.venv/bin/python unavailable', output)

    def test_help_executes_nothing(self):
        with patch('subprocess.Popen', side_effect=AssertionError('must not execute')):
            with self.assertRaises(SystemExit) as result:
                self.invoke(['--help'])
        self.assertEqual(result.exception.code, 0)

    def test_interruption_cleans_up_child(self):
        child = unittest.mock.Mock(pid=12345)
        child.wait.side_effect = [KeyboardInterrupt, 0]
        with patch('subprocess.Popen', return_value=child), patch('os.killpg') as kill:
            with self.assertRaises(KeyboardInterrupt):
                runner['execute'](['fixture'], {}, 1)
        kill.assert_called_once_with(12345, runner['signal'].SIGKILL)
        self.assertEqual(child.wait.call_count, 2)

    def fake_python(self):
        target = self.root / '.venv/bin/python'
        target.parent.mkdir(parents=True)
        target.touch()

    def test_missing_dependencies_skip_suite(self):
        self.fake_python()
        with patch.dict(runner['main'].__globals__, execute=lambda *a: ('FAILED', 'exit 3')):
            code, output = self.invoke(['--run'])
        self.assertEqual(code, 0)
        self.assertIn('required dependencies unavailable', output)

    def test_failed_suite_and_probe_timeout_are_reported(self):
        self.fake_python()
        for results in ([('PASSED', 'exit 0'), ('FAILED', 'exit 7')],
                        [('FAILED', 'timeout after 30s')]):
            with self.subTest(results=results), patch.dict(
                    runner['main'].__globals__, execute=unittest.mock.Mock(side_effect=results)):
                code, output = self.invoke(['--run'])
            self.assertEqual(code, 1)
            self.assertIn('FAILED', output)
            self.assertIn(results[-1][1], output)

    def test_real_failure_timeout_and_isolation(self):
        env = runner['environment'](self.root)
        self.assertNotIn('PYTHONPATH', env)
        self.assertNotIn('API_KEY', env)
        self.assertEqual(env['HF_HUB_OFFLINE'], '1')
        self.assertEqual(env['BROWSER'], 'true')
        self.assertEqual(env['PYTHONDONTWRITEBYTECODE'], '1')
        script = ('import os, pathlib, tempfile; '
                  'assert pathlib.Path.home() == pathlib.Path(os.environ["HOME"]); '
                  'assert tempfile.gettempdir() == os.environ["TMPDIR"]; '
                  'pathlib.Path(os.environ["XDG_DATA_HOME"], "fixture").write_text("generated")')
        status, _ = runner['execute']([sys.executable, '-B', '-c', script], env, 10)
        self.assertEqual(status, 'PASSED')
        self.assertTrue((Path(env['XDG_DATA_HOME']) / 'fixture').is_file())
        self.assertEqual(runner['execute']([sys.executable, '-c', 'raise SystemExit(7)'], env, 10),
                         ('FAILED', 'exit 7'))
        status, detail = runner['execute']([sys.executable, '-c', 'import time; time.sleep(30)'], env, .1)
        self.assertEqual(status, 'FAILED')
        self.assertIn('timeout', detail)


if __name__ == '__main__':
    unittest.main()
