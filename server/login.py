"""Opt-in, next-login launch of this particular macOS bundle and data directory."""
import hashlib
import os
from pathlib import Path
import plistlib
import sys
import tempfile
import threading


class LoginLaunch:
    def __init__(self, data_dir, *, home=None, bundle=None, platform=None):
        self.lock = threading.Lock()
        self.data_dir = Path(data_dir).resolve()
        self.home = Path(home) if home is not None else Path.home()
        self.platform = platform if platform is not None else sys.platform
        candidates = [Path(bundle)] if bundle else [Path(os.environ.get('ORCHARD_BUNDLE', sys.executable)), *Path(sys.executable).parents]
        self.bundle = next((path.absolute() for path in candidates if path.suffix == '.app' and (path / 'Contents/Info.plist').is_file()), None)
        identity = f'{self.bundle}\n{self.data_dir}'
        self.label = 'local.orchard.login.' + hashlib.sha256(identity.encode()).hexdigest()[:16]
        self.path = self.home / 'Library/LaunchAgents' / (self.label + '.plist')

    def status(self):
        available = self.platform == 'darwin' and self.bundle is not None
        enabled = False
        try:
            enabled = available and plistlib.loads(self.path.read_bytes()) == self._configuration()
        except (OSError, ValueError, plistlib.InvalidFileException):
            pass
        return {'available': available, 'enabled': enabled}

    def _configuration(self):
        return {'Label': self.label, 'ProgramArguments': ['/usr/bin/open', str(self.bundle), '--args', '--data-dir', str(self.data_dir)],
                'RunAtLoad': True, 'LimitLoadToSessionType': 'Aqua'}

    def update(self, values):
        if not isinstance(values, dict) or set(values) != {'enabled'} or type(values['enabled']) is not bool:
            raise ValueError('Choose whether Orchard should launch at login.')
        with self.lock:
            if not self.status()['available']:
                raise ValueError('Launch at login is available from the macOS app bundle.')
            if not values['enabled']:
                self.path.unlink(missing_ok=True)
            else:
                # Never load the agent now. macOS reads it at the next graphical login.
                # No KeepAlive means quitting Orchard does not restart it.
                if self.bundle.is_relative_to(Path('/Volumes')) or '/AppTranslocation/' in str(self.bundle):
                    raise ValueError('Move Orchard to a permanent location before enabling launch at login.')
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as stream:
                        temporary = Path(stream.name)
                        plistlib.dump(self._configuration(), stream)
                    temporary.replace(self.path)
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
            return self.status()
