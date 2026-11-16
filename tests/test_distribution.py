import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

from server.library import Library
from server.semantic import Encoder

ROOT = Path(__file__).resolve().parent.parent


class DistributionTests(unittest.TestCase):
    def test_manifest_records_actual_source_hashes(self):
        namespace = runpy.run_path(str(ROOT / 'scripts/build-app'))
        copy = namespace['copy_app']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            (source / 'dist').mkdir(parents=True)
            (source / 'dist/index.html').write_text('review build')
            (source / 'requirements.txt').write_text('onnxruntime==1.23.2\n')
            (source / 'app.json').write_text('{}')
            target = root / 'copied'
            with patch.dict(copy.__globals__, {'ROOT': source, 'FILES': ['dist', 'requirements.txt', 'app.json']}):
                copy(target)
            manifest = json.loads((target / 'BUILD.json').read_text())
            self.assertEqual(manifest['files']['dist/index.html'], hashlib.sha256(b'review build').hexdigest())
            self.assertEqual(manifest['python'], [3, 13])
            self.assertIsNone(manifest['commit'])
            self.assertEqual((target / 'requirements.txt').read_bytes(), (source / 'requirements.txt').read_bytes())

    def test_cached_packages_reject_missing_pins_before_copying(self):
        namespace = runpy.run_path(str(ROOT / 'scripts/build-app'))
        with tempfile.TemporaryDirectory() as temporary, patch('importlib.metadata.distributions', return_value=[]):
            source = Path(temporary) / 'source'
            source.mkdir()
            target = Path(temporary) / 'target'
            with self.assertRaisesRegex(ValueError, 'do not satisfy'):
                namespace['install_packages'](target, source=source)
            self.assertFalse(target.exists())

    def test_rehearsal_reads_real_catalog_and_vector_schema(self):
        namespace = runpy.run_path(str(ROOT / 'scripts/test-distribution'))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = Library(root, root / 'libraries/test', Encoder(root / 'models'))
            digest, vectors = namespace['catalog'](root, 'test')
            self.assertEqual(len(digest), 64)
            self.assertEqual(vectors, 0)
            library.close()
