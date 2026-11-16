from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

from server.login import LoginLaunch


class LoginLaunchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bundle = self.root / 'Orchard Review.app'
        (self.bundle / 'Contents').mkdir(parents=True)
        (self.bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps({}))
        self.options = {'home': self.root / 'home', 'bundle': self.bundle, 'platform': 'darwin'}
        self.login = LoginLaunch(self.root / 'data', **self.options)

    def test_opt_in_persists_and_disable_only_removes_own_agent(self):
        self.assertEqual(self.login.status(), {'available': True, 'enabled': False})
        self.assertFalse(self.login.path.exists())
        self.assertTrue(self.login.update({'enabled': True})['enabled'])
        config = plistlib.loads(self.login.path.read_bytes())
        self.assertEqual(config['ProgramArguments'], ['/usr/bin/open', str(self.bundle), '--args', '--data-dir', str((self.root / 'data').resolve())])
        self.assertTrue(config['RunAtLoad'])
        self.assertNotIn('KeepAlive', config)
        self.assertEqual(config['LimitLoadToSessionType'], 'Aqua')
        reopened = LoginLaunch(self.root / 'data', **self.options)
        self.assertTrue(reopened.status()['enabled'])
        other = self.login.path.parent / 'unrelated.plist'
        other.write_text('unchanged')
        self.assertFalse(reopened.update({'enabled': False})['enabled'])
        self.assertFalse(self.login.path.exists())
        self.assertEqual(other.read_text(), 'unchanged')

    def test_data_directories_and_bundles_are_isolated(self):
        self.login.update({'enabled': True})
        other = LoginLaunch(self.root / 'other-data', **self.options)
        self.assertFalse(other.status()['enabled'])
        self.assertNotEqual(other.path, self.login.path)

    def test_invalid_and_unsupported_requests_do_not_write(self):
        for values in ({}, {'enabled': 1}, {'enabled': True, 'other': True}, None):
            with self.assertRaises(ValueError):
                self.login.update(values)
        unsupported = LoginLaunch(self.root / 'data', **{**self.options, 'platform': 'linux'})
        self.assertFalse(unsupported.status()['available'])
        with self.assertRaises(ValueError):
            unsupported.update({'enabled': True})
        self.assertFalse(self.login.path.exists())

    def test_failed_atomic_save_keeps_prior_setting(self):
        self.login.update({'enabled': True})
        before = self.login.path.read_bytes()
        with patch.object(Path, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.login.update({'enabled': True})
        self.assertEqual(self.login.path.read_bytes(), before)
        self.assertEqual(list(self.login.path.parent.iterdir()), [self.login.path])

    def test_damaged_plist_is_reported_disabled(self):
        self.login.update({'enabled': True})
        self.login.path.write_text('broken')
        self.assertFalse(self.login.status()['enabled'])
