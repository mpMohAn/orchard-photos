"""Low-cost directory-change probes between the periodic full reconciliations."""
import os
from pathlib import Path
import time

from server.cache import connect


class FolderChanges:
    def __init__(self):
        self.library = None
        self.directories = {}
        self.incomplete = {}
        self.updated = None
        self.pending = False
        self.dirty_since = 0

    @staticmethod
    def stamp(path):
        try:
            status = path.stat()
            return status.st_mtime_ns, status.st_size, status.st_ino
        except OSError:
            return None

    def discover(self, roots):
        directories, visited = {}, set()
        cache = self.library.directory.stat()
        excluded = cache.st_dev, cache.st_ino
        stack = list(roots)
        while stack:
            path = Path(stack.pop())
            try:
                status = path.stat()
                identity = status.st_dev, status.st_ino
                if identity in visited or identity == excluded:
                    continue
                visited.add(identity)
                directories[path] = self.stamp(path)
                with os.scandir(path) as entries:
                    for entry in entries:
                        if not entry.name.startswith('.') and not entry.name.endswith('.photoslibrary'):
                            try:
                                if entry.is_dir():
                                    stack.append(Path(entry.path))
                            except OSError:
                                pass
            except OSError:
                directories[path] = None
        return directories

    def changed(self, library):
        if library.photos or library.closed.is_set():
            return False
        if self.library is not library:
            self.library = library
            self.directories = self.discover(library.roots)
            self.incomplete = {}
            self.updated = None
            self.pending = True
        updated = library.stats.get('updated')
        if updated != self.updated:
            self.updated = updated
            with connect(library.directory) as db:
                errors = db.execute('SELECT path,mtime_ns,size FROM files WHERE error IS NOT NULL LIMIT 256').fetchall()
            self.incomplete = {}
            for row in errors:
                try:
                    path = library.scanner.source.file(row[0])
                    self.incomplete[path] = row[1], row[2]
                except (OSError, ValueError):
                    continue
        directories = {path: self.stamp(path) for path in self.directories}
        incomplete = {}
        for path in self.incomplete:
            stamp = self.stamp(path)
            incomplete[path] = stamp[:2] if stamp else None
        if directories != self.directories or incomplete != self.incomplete:
            self.directories = self.discover(library.roots)
            self.incomplete = incomplete
            now = time.monotonic()
            if not self.pending:
                self.dirty_since = now
            self.pending = True
            if now - self.dirty_since < 3:
                return False
        if self.pending:
            self.pending = False
            return True
        return False
