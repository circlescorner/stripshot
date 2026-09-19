"""Durable replacement and a process lock for one appliance owner."""
import fcntl
import json
import os
import tempfile
from pathlib import Path


def atomic_bytes(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def save_json(path, value):
    atomic_bytes(path, (json.dumps(value, indent=2) + '\n').encode())


class ProcessLock:
    def __init__(self, directory, allow_redirect=False):
        Path(directory).mkdir(parents=True, exist_ok=True)
        if not allow_redirect and (Path(directory) / 'storage-redirect.json').exists():
            raise RuntimeError('This storage folder was migrated; use the current launcher and destination')
        if (Path(directory) / 'storage-incomplete.json').exists() and not allow_redirect:
            raise RuntimeError('Storage migration is incomplete; preserve both data trees')
        self.stream = open(Path(directory) / 'stripshot.lock', 'a+')
        try:
            fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.stream.close()
            raise RuntimeError('Stripshot is already using this data directory') from None
        if not allow_redirect and any((Path(directory)/name).exists() for name in ('storage-redirect.json','storage-incomplete.json')):
            self.stream.close()
            raise RuntimeError('Storage was migrated or is incomplete; use the current launcher')

    def close(self):
        self.stream.close()
