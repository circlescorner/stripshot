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
    def __init__(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)
        self.stream = open(Path(directory) / 'stripshot.lock', 'a+')
        try:
            fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.stream.close()
            raise RuntimeError('Stripshot is already using this data directory') from None

    def close(self):
        self.stream.close()
