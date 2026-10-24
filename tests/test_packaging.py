"""Architecture selection must reject cross-architecture dependency installs."""
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

BUILD = Path(__file__).resolve().parent.parent / 'scripts' / 'build-app'


class PackagingTests(unittest.TestCase):
    def test_native_intel_and_arm_builds_are_accepted(self):
        namespace = runpy.run_path(str(BUILD))
        main = namespace['main']
        globals_ = main.__globals__
        for machine in ('x86_64', 'arm64'):
            with self.subTest(machine=machine), tempfile.TemporaryDirectory() as folder:
                artifact = Path(folder) / 'test.dmg'
                artifact.write_bytes(b'dmg')
                with patch.object(sys, 'argv', [str(BUILD), '--out', folder]), \
                        patch.object(sys, 'platform', 'darwin'), patch.object(sys, 'version_info', (3, 13)), \
                        patch('platform.machine', return_value=machine), \
                        patch.dict(globals_, {'build_mac': lambda build, artifact=artifact: artifact}):
                    main()

    def test_unknown_architecture_is_rejected_before_building(self):
        namespace = runpy.run_path(str(BUILD))
        with patch.object(sys, 'argv', [str(BUILD)]), patch.object(sys, 'platform', 'darwin'), \
                patch('platform.machine', return_value='unsupported'), self.assertRaisesRegex(SystemExit, 'builds on Intel'):
            namespace['main']()
