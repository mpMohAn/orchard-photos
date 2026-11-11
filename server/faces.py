"""Opt-in local face detection, embeddings, and editable per-workspace people."""
import hashlib
import io
import json
import os
import secrets
import threading
import time
import urllib.request

import numpy as np
from PIL import Image

from server.cache import connect
from server.scanner import refuse_oversized, scaled

MODELS = (
    ('face_detection_yunet', 'face_detection_yunet_2023mar.onnx', '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4', 232589),
    ('face_recognition_sface', 'face_recognition_sface_2021dec.onnx', '0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79', 38696353),
)
MODEL_VERSION = 'yunet-2023mar-sface-2021dec-v1'
MATCH = .55


class FaceEncoder:
    def __init__(self, directory):
        self.directory = directory
        self.detector = self.recognizer = None

    def load(self, cancelled):
        import onnxruntime as ort

        self.directory.mkdir(parents=True, exist_ok=True)
        paths = []
        for family, name, checksum, limit in MODELS:
            path = self.directory / name
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
                if cancelled():
                    return False
                if os.environ.get('HF_HUB_OFFLINE') == '1':
                    raise RuntimeError('Face models are unavailable in offline mode.')
                temporary = path.with_suffix('.' + secrets.token_hex(6) + '.part')
                try:
                    url = f'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/{family}/{name}'
                    digest = hashlib.sha256()
                    received = 0
                    with urllib.request.urlopen(url, timeout=30) as response, temporary.open('wb') as output:
                        while chunk := response.read(262144):
                            if cancelled():
                                return False
                            received += len(chunk)
                            if received > limit:
                                raise RuntimeError('The face model download was larger than expected.')
                            digest.update(chunk)
                            output.write(chunk)
                    if received != limit or digest.hexdigest() != checksum:
                        raise RuntimeError('Face model verification failed. Retry setup.')
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
            paths.append(path)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        options.add_session_config_entry('session.intra_op.allow_spinning', '0')
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.detector, self.recognizer = [ort.InferenceSession(str(path), options, providers=['CPUExecutionProvider']) for path in paths]
        return True

    def encode(self, original):
        refuse_oversized(original)
        image = scaled(original, 640).convert('RGB')
        width, height = image.size
        canvas = np.zeros((640, 640, 3), np.float32)
        canvas[:height, :width] = np.asarray(image)[:, :, ::-1]
        outputs = self.detector.run(None, {self.detector.get_inputs()[0].name: canvas.transpose(2, 0, 1)[None]})
        data = dict(zip([value.name for value in self.detector.get_outputs()], outputs))
        candidates = []
        for stride in (8, 16, 32):
            scores = np.sqrt(np.clip(data[f'cls_{stride}'].reshape(-1), 0, 1) * np.clip(data[f'obj_{stride}'].reshape(-1), 0, 1))
            for index in np.flatnonzero(scores >= .85):
                grid = np.array([index % (640 // stride), index // (640 // stride)])
                box = data[f'bbox_{stride}'].reshape(-1, 4)[index]
                centre = (box[:2] + grid) * stride
                size = np.exp(np.clip(box[2:], -10, 10)) * stride
                rect = np.r_[centre - size / 2, centre + size / 2]
                if min(size) < 20 or centre[0] >= width or centre[1] >= height:
                    continue
                landmarks = (data[f'kps_{stride}'].reshape(-1, 5, 2)[index] + grid) * stride
                candidates.append((float(scores[index]), rect, landmarks))
        kept = []
        for score, rect, landmarks in sorted(candidates, key=lambda value: -value[0])[:500]:
            area = np.prod(rect[2:] - rect[:2])
            if any(self.overlap(rect, previous[1], area) > .3 for previous in kept):
                continue
            kept.append((score, rect, landmarks))
            if len(kept) == 100:
                break
        result = []
        target = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]])
        for _, rect, source in kept:
            # Inverse similarity transform maps aligned output pixels to source pixels.
            src = source - source.mean(0)
            dst = target - target.mean(0)
            u, singular, vt = np.linalg.svd(dst.T @ src / 5)
            sign = np.diag([1, np.sign(np.linalg.det(u @ vt))])
            rotation = u @ sign @ vt
            scale = (singular * np.diag(sign)).sum() / (src * src).sum() * 5
            if not np.isfinite(scale) or scale <= 0:
                continue
            inverse = np.linalg.inv(scale * rotation)
            offset = source.mean(0) - inverse @ target.mean(0)
            affine = np.column_stack((inverse, offset)).reshape(-1)
            aligned = image.transform((112, 112), Image.Transform.AFFINE, affine, Image.Resampling.BILINEAR)
            pixels = np.asarray(aligned, dtype=np.float32).transpose(2, 0, 1)[None]
            vector = self.recognizer.run(None, {self.recognizer.get_inputs()[0].name: pixels})[0].reshape(-1).astype('<f4')
            norm = np.linalg.norm(vector)
            if not np.isfinite(norm) or norm == 0:
                continue
            crop = io.BytesIO()
            aligned.save(crop, 'WEBP', quality=85)
            result.append((vector / norm, (rect / [width, height, width, height]).clip(0, 1).tolist(), crop.getvalue()))
        return result

    @staticmethod
    def overlap(first, second, area):
        intersection = np.maximum(0, np.minimum(first[2:], second[2:]) - np.maximum(first[:2], second[:2])).prod()
        return intersection / max(1, area + np.prod(second[2:] - second[:2]) - intersection)


class People:
    def __init__(self, library):
        self.library = library
        self.lock = threading.RLock()
        self.worker_lock = threading.Lock()
        self.generation = 0
        self.state = 'off'
        self.error = ''
        with connect(library.directory) as db:
            db.execute('CREATE TABLE IF NOT EXISTS people_settings (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER, paused INTEGER, version TEXT)')
            db.execute('INSERT OR IGNORE INTO people_settings VALUES (1,0,0,?)', (MODEL_VERSION,))
            db.execute('CREATE TABLE IF NOT EXISTS people (id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT "")')
            db.execute('CREATE TABLE IF NOT EXISTS faces (id TEXT PRIMARY KEY, image_id TEXT, person TEXT, box TEXT, vector BLOB, crop BLOB, ignored INTEGER DEFAULT 0)')
            db.execute('CREATE INDEX IF NOT EXISTS faces_person ON faces(person)')
            db.execute('CREATE INDEX IF NOT EXISTS faces_image ON faces(image_id)')
            db.execute('CREATE TABLE IF NOT EXISTS faces_processed (image_id TEXT PRIMARY KEY)')
            settings = db.execute('SELECT enabled,paused,version FROM people_settings').fetchone()
        self.enabled, self.paused = map(bool, settings[:2])
        self.compatible = settings[2] == MODEL_VERSION
        if not self.compatible:
            self.enabled = False
            self.state, self.error = 'error', 'Existing face data uses another model version. Clear face data explicitly before setting up this version.'

    def status(self):
        with self.lock, connect(self.library.directory, rows=True) as db:
            db.execute('DELETE FROM faces WHERE image_id NOT IN (SELECT id FROM images)')
            db.execute('DELETE FROM faces_processed WHERE image_id NOT IN (SELECT id FROM images)')
            processed = db.execute('SELECT count(*) FROM faces_processed').fetchone()[0]
            total = db.execute('SELECT count(*) FROM images').fetchone()[0]
            groups = [dict(row) for row in db.execute('''SELECT p.id,p.name,count(DISTINCT f.image_id) AS photos,min(f.id) AS cover
                FROM people p JOIN faces f ON f.person=p.id WHERE f.ignored=0 GROUP BY p.id ORDER BY photos DESC,p.id''')]
            return {'enabled': self.enabled, 'paused': self.paused, 'state': self.state, 'error': self.error, 'processed': processed, 'total': total, 'people': groups}

    def start(self):
        if self.compatible and self.enabled and not self.paused and not self.library.closed.is_set() and self.worker_lock.acquire(blocking=False):
            threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        generation = self.generation
        def cancelled():
            return self.library.closed.is_set() or not self.enabled or self.paused or self.generation != generation
        encoder = FaceEncoder(self.library.semantic.encoder.cache / 'faces')
        interrupted = True
        try:
            with connect(self.library.directory) as db:
                pending = db.execute('SELECT 1 FROM images WHERE id NOT IN (SELECT image_id FROM faces_processed) LIMIT 1').fetchone()
            if not pending:
                self.state, self.error = 'ready', ''
                interrupted = False
                return
            self.state, self.error = 'loading', ''
            if not encoder.load(cancelled) or cancelled():
                return
            self.state = 'indexing'
            while not cancelled():
                # Yield to the existing visual index and folder scans.
                if self.library.semantic_lock.locked() or self.library.scan_lock.locked() or self.library.layout.status()['state'] == 'computing':
                    time.sleep(.25)
                    continue
                with connect(self.library.directory) as db:
                    row = db.execute('SELECT id FROM images WHERE id NOT IN (SELECT image_id FROM faces_processed) ORDER BY id LIMIT 1').fetchone()
                if not row:
                    break
                image_id = row[0]
                path = self.library.original(image_id)
                if path is None:
                    raise RuntimeError('A photo is unavailable. Reconnect its folder and resume.')
                with path.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != image_id:
                        raise RuntimeError('A photo changed. Rescan the library before resuming People indexing.')
                    stream.seek(0)
                    with Image.open(stream) as image:
                        image.draft('RGB', (1280, 1280))
                        found = encoder.encode(image)
                with self.lock, connect(self.library.directory) as db:
                    if cancelled():
                        break
                    for vector, box, crop in found:
                        self._store(db, image_id, vector, box, crop)
                    db.execute('INSERT OR IGNORE INTO faces_processed VALUES (?)', (image_id,))
                if found:
                    self.library.revision += 1
                time.sleep(.05)
            if not cancelled():
                self.state = 'ready'
                interrupted = False
        except Exception:
            self.state, self.error = 'error', 'People indexing stopped. Check that the folder is available and resume. Model setup needs an internet connection once.'
        finally:
            del encoder
            self.worker_lock.release()
            if cancelled():
                self.state = 'paused' if self.enabled else 'off'
            if interrupted and self.state != 'error' and self.enabled and not self.paused and not self.library.closed.is_set():
                self.start()

    @staticmethod
    def _store(db, image_id, vector, box, crop):
        matches = []
        for person, stored in db.execute('SELECT person,vector FROM faces WHERE ignored=0 AND person NOT IN (SELECT person FROM faces WHERE image_id=? AND ignored=0) GROUP BY person', (image_id,)):
            reference = np.frombuffer(stored, dtype='<f4')
            if reference.shape == vector.shape:
                matches.append((float(reference @ vector), person))
        matches.sort(reverse=True)
        person = matches[0][1] if matches and matches[0][0] >= MATCH and (len(matches) == 1 or matches[0][0] - matches[1][0] >= .06) else secrets.token_hex(8)
        db.execute('INSERT OR IGNORE INTO people(id) VALUES (?)', (person,))
        db.execute('INSERT INTO faces VALUES (?,?,?,?,?,?,0)', (secrets.token_hex(12), image_id, person, json.dumps(box), vector.astype('<f4').tobytes(), crop))

    def members(self, person):
        with self.lock, connect(self.library.directory, rows=True) as db:
            return [dict(row) for row in db.execute('''SELECT id,image_id,box FROM faces WHERE person=? AND ignored=0
                AND image_id IN (SELECT id FROM images) ORDER BY image_id,id''', (person,))]

    def crop(self, face):
        with self.lock, connect(self.library.directory) as db:
            row = db.execute('SELECT crop FROM faces WHERE id=? AND ignored=0', (face,)).fetchone()
            return row[0] if row else None

    def update(self, values):
        if not isinstance(values, dict):
            raise ValueError('Choose a supported People action.')
        action = values.get('action')
        if action in {'enable', 'resume'} and not self.compatible:
            raise ValueError('Clear the older face data explicitly before enabling this model version.')
        with self.lock, connect(self.library.directory) as db:
            enabled, paused = self.enabled, self.paused
            if action == 'enable':
                if values.get('consent') is not True:
                    raise ValueError('Confirm local face processing before enabling People.')
                enabled, paused = True, False
            elif action == 'pause':
                paused = True
            elif action == 'resume':
                if not self.enabled:
                    raise ValueError('Enable People first.')
                paused = False
            elif action == 'clear':
                if values.get('confirmed') is not True:
                    raise ValueError('Confirm clearing face data.')
                db.execute('PRAGMA secure_delete=ON')
                enabled, paused = False, False
                db.execute('UPDATE people_settings SET version=? WHERE id=1', (MODEL_VERSION,))
                for table in ('faces', 'people', 'faces_processed'):
                    db.execute(f'DELETE FROM {table}')
            elif action == 'name':
                name = values.get('name')
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
                    raise ValueError('Use a name of 1–80 characters.')
                db.execute('UPDATE people SET name=? WHERE id=?', (name.strip(), values.get('person')))
            elif action == 'merge':
                source, target = values.get('source'), values.get('target')
                if source == target or db.execute('SELECT count(*) FROM people WHERE id IN (?,?)', (source, target)).fetchone()[0] != 2:
                    raise ValueError('Choose two different people.')
                db.execute('UPDATE faces SET person=? WHERE person=?', (target, source))
                db.execute('DELETE FROM people WHERE id=?', (source,))
            elif action in {'separate', 'ignore', 'assign'}:
                face = values.get('face')
                if not isinstance(face, str) or not db.execute('SELECT 1 FROM faces WHERE id=? AND ignored=0', (face,)).fetchone():
                    raise ValueError('Choose a detected face.')
                if action == 'assign':
                    person = values.get('person')
                    if person:
                        if not isinstance(person, str) or not db.execute('SELECT 1 FROM people WHERE id=?', (person,)).fetchone():
                            raise ValueError('Choose an existing person.')
                    else:
                        name = values.get('name')
                        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
                            raise ValueError('Use a name of 1–80 characters.')
                        person = secrets.token_hex(8)
                        db.execute('INSERT INTO people(id,name) VALUES (?,?)', (person, name.strip()))
                    db.execute('UPDATE faces SET person=? WHERE id=?', (person, face))
                elif action == 'ignore':
                    db.execute('UPDATE faces SET ignored=1,vector=NULL,crop=NULL WHERE id=?', (face,))
                else:
                    person = secrets.token_hex(8)
                    db.execute('INSERT INTO people(id) VALUES (?)', (person,))
                    db.execute('UPDATE faces SET person=? WHERE id=?', (person, face))
            else:
                raise ValueError('Choose a supported People action.')
            db.execute('UPDATE people_settings SET enabled=?,paused=? WHERE id=1', (enabled, paused))
            db.commit()
            self.enabled, self.paused = enabled, paused
            if action == 'clear':
                self.state, self.error = 'off', ''
                self.compatible = True
                self.generation += 1
        self.library.revision += 1
        if action in {'enable', 'resume'}:
            self.start()
        return self.status()
