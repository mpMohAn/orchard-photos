"""Explicit duplicate review and journaled macOS Trash operations."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import sys
import threading
import time

from server.cache import connect

MAX_SELECTION = 50
PLAN_SECONDS = 600


def trash_available():
    return sys.platform == 'darwin' and importlib.util.find_spec('Foundation') is not None


def move_to_trash(path):
    """Use macOS Trash, retaining the resulting location for recovery."""
    from Foundation import NSURL, NSFileManager
    import objc

    with objc.autorelease_pool():
        success, destination, error = NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(
            NSURL.fileURLWithPath_(str(path)), None, None)
        if not success:
            raise OSError(str(error.localizedDescription()) if error else 'macOS could not move this file to Trash.')
        return str(destination.path()) if destination else ''


class Duplicates:
    def __init__(self, library):
        self.library = library
        self.lock = threading.Lock()
        with connect(library.directory) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS duplicate_reviews (
                token TEXT PRIMARY KEY, created REAL NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL
            )''')

    def _groups(self, kind):
        if kind not in {'exact', 'similar'}:
            raise ValueError('Choose exact copies or similar photos.')
        with connect(self.library.directory, rows=True) as db:
            if kind == 'exact':
                rows = db.execute('''SELECT i.id, count(*) AS copies, i.size * (count(*) - 1) AS extra
                                     FROM images i JOIN files f ON f.image_id=i.id
                                     GROUP BY i.id HAVING count(*)>1 ORDER BY extra DESC,i.id''').fetchall()
            else:
                rows = db.execute('''SELECT g.group_id AS id, count(DISTINCT i.id) AS copies, sum(i.size) AS extra
                                     FROM image_groups g JOIN images i ON i.id=g.image_id
                                     WHERE EXISTS (SELECT 1 FROM files f WHERE f.image_id=i.id)
                                     GROUP BY g.group_id HAVING count(DISTINCT i.id)>1 ORDER BY extra DESC,g.group_id''').fetchall()
        return rows

    def group(self, kind, group_id):
        if kind not in {'exact', 'similar'} or not isinstance(group_id, str) or len(group_id) != 64:
            raise ValueError('Choose a duplicate group.')
        with connect(self.library.directory, rows=True) as db:
            if kind == 'exact':
                images = db.execute('SELECT * FROM images WHERE id=?', (group_id,)).fetchall()
            else:
                images = db.execute('''SELECT i.* FROM images i JOIN image_groups g ON g.image_id=i.id
                                       WHERE g.group_id=? ORDER BY g.score DESC,i.id''', (group_id,)).fetchall()
            result = []
            for image in images:
                files = [dict(row) for row in db.execute('SELECT path,size,modified FROM files WHERE image_id=? ORDER BY path', (image['id'],))]
                if files:
                    result.append({**dict(image), 'files': files})
        if (kind == 'exact' and (not result or len(result[0]['files']) < 2)) or (kind == 'similar' and len(result) < 2):
            raise ValueError('This group changed. Refresh duplicate review.')
        return {'id': group_id, 'kind': kind, 'images': result}

    def list(self, params):
        kind = params.get('kind', 'exact')
        groups = self._groups(kind)
        offset = max(0, int(params.get('offset', '0')))
        limit = min(30, max(1, int(params.get('limit', '12'))))
        items = []
        for row in groups[offset:offset + limit]:
            try:
                group = self.group(kind, row['id'])
            except ValueError:
                continue  # A background scan or grouping pass may have changed it.
            files = [file for image in group['images'] for file in image['files']]
            group['extraBytes'] = sum(file['size'] for file in files) - max(file['size'] for file in files)
            items.append(group)
        return {'items': items, 'total': len(groups), 'offset': offset, 'hasMore': offset + limit < len(groups),
                'nextOffset': min(len(groups), offset + limit), 'trashAvailable': trash_available() and not self.library.photos}

    def _inspect(self, image_id, relative):
        if self.library.path(image_id, relative) != relative:
            raise ValueError('A selected file is no longer in this catalog. Refresh duplicate review.')
        path = self.library.scanner.source.file(relative)
        resolved = path.resolve(strict=True)
        if resolved != path.absolute() or not any(resolved.is_relative_to(root) for root in self.library.roots):
            raise ValueError('Symlinked files cannot be moved from duplicate review.')
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)), 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError('Only regular, independently stored files can be moved from duplicate review.')
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            after = os.fstat(stream.fileno())
        fingerprint = [after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns]
        current = path.stat(follow_symlinks=False)
        if digest != image_id or [before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns] != fingerprint or fingerprint != [current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns]:
            raise ValueError('A file changed since it was indexed. Rescan and review it again.')
        return {'id': image_id, 'path': relative, 'original': str(path), 'size': after.st_size, 'fingerprint': fingerprint}

    def _writable(self):
        if self.library.closed.is_set():
            raise ValueError('The library changed. Open duplicate review again.')
        if self.library.photos or not trash_available():
            raise ValueError('Trash cleanup is available for regular folders on macOS.')

    def plan(self, values):
        self._writable()
        selected = values.get('paths')
        if not isinstance(selected, list) or not 1 <= len(selected) <= MAX_SELECTION or any(not isinstance(path, str) for path in selected) or len(set(selected)) != len(selected):
            raise ValueError(f'Choose between 1 and {MAX_SELECTION} distinct files to move.')
        group = self.group(values.get('kind'), values.get('group'))
        files = [(image['id'], file['path']) for image in group['images'] for file in image['files']]
        if not set(selected) < {path for _, path in files}:
            raise ValueError('Keep at least one file in this group and select only files from this group.')
        moving = [self._inspect(image_id, path) for image_id, path in files if path in selected]
        keeper_id, keeper_path = next((image_id, path) for image_id, path in files if path not in selected)
        kept = [self._inspect(keeper_id, keeper_path)]
        token = secrets.token_hex(32)
        payload = {'kind': group['kind'], 'group': group['id'], 'files': [{**file, 'state': 'pending'} for file in moving], 'kept': kept}
        with self.lock, connect(self.library.directory) as db:
            db.execute('INSERT INTO duplicate_reviews VALUES (?,?,?,?)', (token, time.time(), 'planned', json.dumps(payload)))
        return {'token': token, 'files': moving, 'kept': kept, 'bytes': sum(file['size'] for file in moving), 'expiresIn': PLAN_SECONDS}

    def _save(self, token, state, payload, removed=None):
        with connect(self.library.directory) as db:
            db.execute('UPDATE duplicate_reviews SET state=?,payload=? WHERE token=?', (state, json.dumps(payload), token))
            if removed:
                db.execute('DELETE FROM files WHERE path=? AND image_id=?', (removed['path'], removed['id']))
                db.execute('DELETE FROM images WHERE id NOT IN (SELECT image_id FROM files WHERE image_id IS NOT NULL)')

    def plan_files(self, values):
        """Review explicitly selected originals, or every indexed file in a folder. No keeper is required."""
        self._writable()
        if not isinstance(values, dict) or set(values) not in ({'paths'}, {'folder'}):
            raise ValueError('Choose files or one folder to review.')
        with self.lock, self.library.scan_lock:
            with connect(self.library.directory) as db:
                if 'folder' in values:
                    folder = values['folder']
                    if not isinstance(folder, str):
                        raise ValueError('Choose a folder.')
                    where, parameters = self.library.filters({'folder': folder})
                    rows = db.execute('SELECT i.id,f.path FROM files f JOIN images i ON i.id=f.image_id WHERE ' + ' AND '.join(where) + ' ORDER BY f.path LIMIT 5001', parameters).fetchall()
                else:
                    paths = values['paths']
                    if not isinstance(paths, list) or not paths or len(paths) > 5000 or any(not isinstance(path, str) for path in paths) or len(set(paths)) != len(paths):
                        raise ValueError('Choose up to 5,000 distinct files per review.')
                    rows = db.execute('SELECT image_id,path FROM files WHERE image_id IS NOT NULL AND path IN (' + ','.join('?' for _ in paths) + ') ORDER BY path', paths).fetchall()
                    if len(rows) != len(paths):
                        raise ValueError('The selection changed. Refresh and review it again.')
            if not rows or len(rows) > 5000:
                raise ValueError('Choose between 1 and 5,000 indexed files per review. Use a smaller subfolder if needed.')
            moving = [self._inspect(image_id, path) for image_id, path in rows]
            token = secrets.token_hex(32)
            payload = {'kind': 'selected', 'group': '', 'files': [{**file, 'state': 'pending'} for file in moving], 'kept': []}
            with connect(self.library.directory) as db:
                db.execute('INSERT INTO duplicate_reviews VALUES (?,?,?,?)', (token, time.time(), 'planned', json.dumps(payload)))
        return {'token': token, 'files': moving, 'bytes': sum(file['size'] for file in moving), 'expiresIn': PLAN_SECONDS}

    def _verify(self, file):
        current = self._inspect(file['id'], file['path'])
        if current['fingerprint'] != file['fingerprint'] or current['original'] != file['original']:
            raise ValueError('A reviewed file changed. Start a new review.')
        return Path(current['original'])

    @staticmethod
    def _result(token, state, payload):
        return {'token': token, 'state': state, 'files': payload['files'],
                'moved': sum(file['state'] == 'moved' for file in payload['files']),
                'recovery': 'Open macOS Trash and use Put Back, or move the file to its recorded original location. Then rescan Orchard.'}

    def execute(self, values):
        if values.get('confirmed') is not True:
            raise ValueError('Confirm the reviewed files before moving them to Trash.')
        token = values.get('token')
        if not isinstance(token, str):
            raise ValueError('Review the files before confirming.')
        with self.lock, self.library.scan_lock:
            self._writable()
            with connect(self.library.directory, rows=True) as db:
                row = db.execute('SELECT * FROM duplicate_reviews WHERE token=?', (token,)).fetchone()
            if not row:
                raise ValueError('This review is not in the current workspace.')
            payload = json.loads(row['payload'])
            if row['state'] != 'planned':
                return self._result(token, row['state'], payload)
            if time.time() - row['created'] > PLAN_SECONDS:
                raise ValueError('This review expired. Review the files again.')
            for file in payload['files'] + payload['kept']:
                self._verify(file)
            self._save(token, 'executing', payload)
            for file in payload['files']:
                try:
                    path = self._verify(file)
                    for kept in payload['kept']:
                        self._verify(kept)
                    file['state'] = 'moving'
                    self._save(token, 'executing', payload)
                    destination = move_to_trash(path)
                except (OSError, ValueError) as error:
                    file.update(state='failed', error=str(error))
                    break
                file.update(state='moved', trash=destination)
                # If journaling fails after the native move, leave its durable 'moving' marker for manual recovery.
                try:
                    self._save(token, 'executing', payload, removed=file)
                except (OSError, sqlite3.Error):
                    raise RuntimeError('A file may have reached Trash before its result was saved. Check Recent Trash operations and macOS Trash before starting another review.') from None
                self.library.revision += 1
            state = 'complete' if all(file['state'] == 'moved' for file in payload['files']) else 'partial'
            self._save(token, state, payload)
            return self._result(token, state, payload)

    def history(self):
        with connect(self.library.directory, rows=True) as db:
            rows = db.execute("SELECT * FROM duplicate_reviews WHERE state!='planned' ORDER BY created DESC LIMIT 10").fetchall()
        return [self._result(row['token'], row['state'], json.loads(row['payload'])) for row in rows]
