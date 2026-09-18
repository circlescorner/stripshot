"""Read-only camera adapters. Each live PTP connection has one owning thread."""
import io
import json
import posixpath
import queue
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from PIL import Image, ImageDraw
from storage import atomic_bytes


def identity(folder, name, size, mtime):
    return {'folder': folder, 'name': name, 'size': int(size), 'mtime': int(mtime)}


def key(item):
    return json.dumps(item, sort_keys=True, separators=(',', ':'))


def ordered(items):
    return sorted(items, key=lambda x: (x['mtime'], x['folder'], x['name']))


class GPhotoCamera:
    def __init__(self, port, serial):
        self.port, self.serial = port, serial
        self.camera = None

    def open(self):
        import gphoto2 as gp
        self.gp = gp
        self.camera = gp.Camera()
        ports = gp.PortInfoList()
        ports.load()
        self.camera.set_port_info(ports[ports.lookup_path(self.port)])
        self.camera.init()
        actual = str(self.camera.get_single_config('serialnumber').get_value()).strip()
        if actual != self.serial:
            raise RuntimeError(f'Camera serial mismatch on {self.port}: expected {self.serial}, got {actual}')

    def describe(self, folder, name):
        info = self.camera.file_get_info(folder, name).file
        if info.size <= 0:
            raise RuntimeError(f'Camera reported an incomplete file: {folder}/{name}')
        return identity(folder, name, info.size, info.mtime)

    def snapshot(self):
        result = []
        def walk(folder):
            for name, _ in self.camera.folder_list_files(folder):
                if name.lower().endswith(('.jpg', '.jpeg')):
                    result.append(self.describe(folder, name))
            for name, _ in self.camera.folder_list_folders(folder):
                walk(posixpath.join(folder, name))
        walk('/')
        return ordered(result)

    def event(self):
        kind, data = self.camera.wait_for_event(200)
        if kind == self.gp.GP_EVENT_FILE_ADDED and data.name.lower().endswith(('.jpg', '.jpeg')):
            return self.describe(data.folder, data.name)
        return None

    def download(self, item, destination):
        if self.describe(item['folder'], item['name']) != item:
            raise RuntimeError('Camera file changed since it was assigned to this batch')
        file = self.camera.file_get(item['folder'], item['name'], self.gp.GP_FILE_TYPE_NORMAL)
        data = bytes(file.get_data_and_size())
        if len(data) != item['size']:
            raise RuntimeError('Incomplete camera download')
        atomic_bytes(destination, data)

    def close(self):
        if self.camera is not None:
            self.camera.exit()


def discover():
    import gphoto2 as gp
    found = []
    for model, port in gp.Camera.autodetect():
        camera = gp.Camera()
        try:
            ports = gp.PortInfoList()
            ports.load()
            camera.set_port_info(ports[ports.lookup_path(port)])
            camera.init()
            serial = str(camera.get_single_config('serialnumber').get_value()).strip()
            found.append({'model': model, 'port': port, 'serial': serial})
        finally:
            camera.exit()
    return found


def live_cameras(config):
    # Discovery is read-only and done once before the persistent workers start.
    found = discover()
    result = {}
    for label in ('A', 'B'):
        serial = config['cameras'][label]['serial']
        matches = [x for x in found if x['serial'] == serial]
        if len(matches) != 1:
            raise RuntimeError(f'Expected one Camera {label} with serial {serial}; found {len(matches)}')
        result[label] = GPhotoCamera(matches[0]['port'], serial)
    return result


class DemoCamera:
    """Local folders behave like SD cards; their contents survive application restarts."""
    def __init__(self, directory, label):
        self.directory = Path(directory) / label
        self.directory.mkdir(parents=True, exist_ok=True)
        self.label = label
        self.known = set()

    def open(self):
        pass

    def snapshot(self):
        items = [identity('/', p.name, p.stat().st_size, p.stat().st_mtime_ns)
                 for p in self.directory.glob('*.jpg')]
        self.known.update(key(i) for i in items)
        return ordered(items)

    def event(self):
        time.sleep(0.05)
        for p in sorted(self.directory.glob('*.jpg')):
            item = identity('/', p.name, p.stat().st_size, p.stat().st_mtime_ns)
            if key(item) not in self.known:
                self.known.add(key(item))
                return item
        return None

    def download(self, item, destination):
        path = self.directory / item['name']
        if identity('/', path.name, path.stat().st_size, path.stat().st_mtime_ns) != item:
            raise RuntimeError('Demo file changed')
        atomic_bytes(destination, path.read_bytes())

    def shoot(self, count=8):
        for number in range(1, count + 1):
            img = Image.new('RGB', (1200, 800), '#416f77' if self.label == 'A' else '#bc7453')
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle((50, 50, 1150, 750), radius=45, outline='white', width=5)
            draw.text((125, 260), f'{self.label}{number}', fill='white', font_size=160)
            draw.text((135, 470), 'STRIPSHOT / CAMERA ' + self.label, fill='white', font_size=35)
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=92)
            atomic_bytes(self.directory / f'{time.time_ns()}-{number:02d}.jpg', buf.getvalue())

    def close(self):
        pass


class CameraWorker(threading.Thread):
    def __init__(self, label, adapter, events, mode='events', poll_seconds=2):
        super().__init__(name='camera-' + label, daemon=True)
        self.label, self.adapter, self.events = label, adapter, events
        self.mode, self.poll_seconds = mode, poll_seconds
        self.commands = queue.Queue()
        self.stopping = threading.Event()
        self.failure = None
        self.ready = Future()

    def request(self, method, *args):
        future = Future()
        if self.failure:
            future.set_exception(RuntimeError(self.failure))
        elif self.stopping.is_set():
            future.set_exception(RuntimeError('Camera worker is stopping'))
        else:
            self.commands.put((method, args, future))
        return future

    def run(self):
        try:
            self.adapter.open()
            initial = self.adapter.snapshot()
            observed = {key(i) for i in initial}
            self.ready.set_result(initial)
            next_poll = time.monotonic() + self.poll_seconds
            while not self.stopping.is_set():
                try:
                    method, args, future = self.commands.get_nowait()
                except queue.Empty:
                    future = None
                if future is not None:
                    try:
                        future.set_result(getattr(self.adapter, method)(*args))
                    except Exception as exc:
                        future.set_exception(exc)
                        raise
                    continue
                if self.mode == 'events':
                    item = self.adapter.event()
                    if item:
                        self.events.put((self.label, item, None))
                elif time.monotonic() >= next_poll:
                    items = self.adapter.snapshot()
                    for item in items:
                        if key(item) not in observed:
                            self.events.put((self.label, item, None))
                    observed = {key(i) for i in items}
                    next_poll = time.monotonic() + self.poll_seconds
                else:
                    self.stopping.wait(0.05)
        except Exception as exc:
            self.failure = str(exc)
            if not self.ready.done():
                self.ready.set_exception(exc)
            self.events.put((self.label, None, self.failure))
        finally:
            self.stopping.set()
            while True:
                try:
                    _, _, future = self.commands.get_nowait()
                    future.set_exception(RuntimeError(self.failure or 'Camera worker stopped'))
                except queue.Empty:
                    break
            try:
                self.adapter.close()
            except Exception:
                pass
