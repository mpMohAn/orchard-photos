"""Persistent controls for visual indexing; completed embeddings are never discarded."""
from contextlib import contextmanager
import json
from pathlib import Path
import threading


class IndexingControls:
    def __init__(self, path: Path):
        self.path = path
        self.condition = threading.Condition()
        self.paused = False
        self.threads = 0
        try:
            saved = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(saved, dict):
                self.paused = saved.get('paused') is True
                threads = saved.get('threads', 0)
                self.threads = threads if type(threads) is int and 0 <= threads <= 64 else 0
        except (OSError, ValueError):
            pass

    def status(self):
        with self.condition:
            return {'paused': self.paused, 'threads': self.threads}

    def update(self, values):
        if not isinstance(values, dict) or not values or set(values) - {'paused', 'threads'}:
            raise ValueError('Provide paused or threads for visual indexing.')
        if 'paused' in values and type(values['paused']) is not bool:
            raise ValueError('paused must be true or false.')
        if 'threads' in values and (type(values['threads']) is not int or not 0 <= values['threads'] <= 64):
            raise ValueError('CPU threads must be between 0 (automatic) and 64. Changes apply after restarting Orchard.')
        with self.condition:
            settings = {'paused': values.get('paused', self.paused), 'threads': values.get('threads', self.threads)}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            try:
                temporary.write_text(json.dumps(settings), encoding='utf-8')
                temporary.replace(self.path)
            finally:
                temporary.unlink(missing_ok=True)
            self.paused, self.threads = settings['paused'], settings['threads']
            self.condition.notify_all()
            return settings

    def checkpoint(self, cancelled):
        """Pause between batches; closing a library still interrupts a paused worker."""
        with self.condition:
            while self.paused and not cancelled():
                self.condition.wait(.1)
            return not cancelled()


class InferenceQueue:
    """FIFO compute turns shared by visual and People indexing."""
    def __init__(self):
        self.condition = threading.Condition()
        self.waiters = []
        self.busy = False

    @contextmanager
    def turn(self, cancelled):
        ticket = object()
        admitted = False
        with self.condition:
            self.waiters.append(ticket)
            while not cancelled() and (self.busy or self.waiters[0] is not ticket):
                self.condition.wait(.05)
            if not cancelled():
                self.busy = True
                admitted = True
            self.waiters.remove(ticket)
            self.condition.notify_all()
        try:
            yield admitted
        finally:
            if admitted:
                with self.condition:
                    self.busy = False
                    self.condition.notify_all()
