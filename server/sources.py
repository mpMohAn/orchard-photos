"""Several explicitly selected folders, namespaced into one scanner catalog."""
from pathlib import Path, PurePosixPath

from server.scanner import Folder


class Folders:
    def __init__(self, roots, directory):
        self.directory = Path(directory)
        self.roots = {}
        for root in roots:
            name = root.name or str(root)
            prefix = name
            number = 2
            while prefix.casefold() in {value.casefold() for value in self.roots}:
                prefix = f'{name} ({number})'
                number += 1
            self.roots[prefix] = root

    def check(self):
        # A missing root aborts before removals, preserving its existing catalog entries.
        for root in self.roots.values():
            Folder(root).check()

    def list(self, found=None):
        status = self.directory.stat()
        skip = {(status.st_dev, status.st_ino)}
        entries, unreadable, libraries, skipped = [], [], [], {}
        for prefix, root in self.roots.items():
            offset = len(entries)
            progress = (lambda count, start=offset: found(start + count)) if found else None
            files, blocked, photo_libraries, counts = Folder(root, skip).list(progress)
            entries.extend((f'{prefix}/{path}', f'{prefix}/{folder}' if folder else prefix, size, modified)
                           for path, folder, size, modified in files)
            unreadable.extend(f'{prefix}/{path}' if path else prefix for path in blocked)
            libraries.extend(str(root / path) for path in photo_libraries)
            for kind, count in counts.items():
                skipped[kind] = skipped.get(kind, 0) + count
        return entries, unreadable, libraries, skipped

    def file(self, path):
        parts = PurePosixPath(path).parts
        if len(parts) < 2 or parts[0] not in self.roots or '..' in parts:
            raise ValueError('Choose an image from this workspace.')
        # Native path parsing also catches drive-qualified paths and Windows backslash traversal.
        relative = Path(*parts[1:])
        if relative.anchor or '..' in relative.parts:
            raise ValueError('Choose an image from this workspace.')
        return self.roots[parts[0]] / relative

    def open(self, path):
        return self.file(path).open('rb')
