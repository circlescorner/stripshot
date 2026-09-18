"""Camera adapters. Each live PTP connection has one owning thread.

USB previews and explicit software shutters share the same owning thread.
"""
import io
import json
import posixpath
import queue
import threading
import time
from concurrent.futures import Future
from collections import deque
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
    def __init__(self, port, serial, excluded_ports=()):
        self.port, self.serial = port, serial
        self.excluded_ports = set(excluded_ports)
        self.camera = None
        self.preview_started = False
        self.keepalive_next_at = 0
        self.stage = 'not opened'
        self.scan_trace = None
        self.scan_cancelled = lambda: False
        self.scan_progress = None

    def open(self):
        self.stage = 'opening PTP session and reading serial'
        import gphoto2 as gp
        self.gp = gp
        if self.port is None:
            # Re-enumeration belongs to this new owning worker. Never touch a
            # healthy worker's port, inventory the SD card, or trigger a shutter.
            for model, port in gp.Camera.autodetect():
                if port in self.excluded_ports or 'D3300' not in model:
                    continue
                candidate = GPhotoCamera(port, self.serial)
                try:
                    candidate.open()
                except Exception:
                    try:
                        candidate.close()
                    except Exception:
                        # Retain the handle for worker cleanup. Never probe a
                        # second port after an unconfirmed USB release.
                        self.camera = candidate.camera
                        raise
                    continue
                self.port, self.camera = candidate.port, candidate.camera
                candidate.camera = None
                self.stage = 'serial verified after reconnect'
                return
            raise RuntimeError('The expected camera serial is not connected; check USB and power')
        self.camera = gp.Camera()
        ports = gp.PortInfoList()
        ports.load()
        self.camera.set_port_info(ports[ports.lookup_path(self.port)])
        self.camera.init()
        actual = str(self.camera.get_single_config('serialnumber').get_value()).strip()
        if actual != self.serial:
            raise RuntimeError(f'Camera serial mismatch on {self.port}: expected {self.serial}, got {actual}')

    def _capture_once(self, record):
        if self.scan_cancelled():
            raise RuntimeError('Probe cancelled before capture')
        self.stage = 'ending live view for one software capture'
        self._set('viewfinder', 0)
        if self.camera.get_single_config('viewfinder').get_value():
            raise RuntimeError('Live view did not stop')
        self._set('recordingmedia', 'Card')
        previous = self.camera.get_single_config('capturetarget').get_value()
        try:
            self._set('capturetarget', 'Memory card')
            if self._media() != 'Card' or self.camera.get_single_config('capturetarget').get_value() != 'Memory card':
                raise RuntimeError('Card capture destination not verified')
            if self.scan_cancelled():
                raise RuntimeError('Probe cancelled before capture')
            # Persist before triggering. Any failure after this point is uncertain:
            # no automatic retry, even if no returned path was received.
            record('capture_intent', {'count': 1, 'target': 'Memory card'})
            self.stage = 'issuing ONE software capture; no automatic retry'
            path = self.camera.capture(self.gp.GP_CAPTURE_IMAGE)
            captured = {'folder': path.folder, 'name': path.name}
            record('capture_returned', captured)
            if self._media() != 'Card':
                raise RuntimeError('Recording media changed during capture')
        finally:
            self._set('capturetarget', previous)
        return captured

    def software_shot(self, known, destination, record, preview_enabled):
        from render import validate_jpeg
        import hashlib
        captured = self._capture_once(record)
        if not captured['name'].lower().endswith(('.jpg', '.jpeg')):
            raise RuntimeError('Capture returned a non-JPEG path; hold for investigation, no retry')
        item = self.describe(captured['folder'], captured['name'])
        if key(item) in known:
            raise RuntimeError('Capture returned an already assigned file; no retry')
        record('identified', item)
        self.download(item, destination)
        validate_jpeg(destination)
        record('downloaded', {'sha256': hashlib.sha256(Path(destination).read_bytes()).hexdigest()})
        if self.scan_cancelled():
            raise RuntimeError('Stopped before preview restart')
        if preview_enabled:
            frame = self.start_preview()
            record('preview_restarted', {})
            return frame
        return None

    def describe(self, folder, name):
        info = self.camera.file_get_info(folder, name).file
        if info.size <= 0:
            raise RuntimeError(f'Camera reported an incomplete file: {folder}/{name}')
        return identity(folder, name, info.size, info.mtime)

    def snapshot(self):
        # Keep full metadata identity: a partial scan must never become a baseline.
        result = []
        started = time.monotonic()
        sequence = 0

        def operation(method, *args):
            nonlocal sequence
            if self.scan_cancelled():
                raise RuntimeError('SD scan cancelled; baseline incomplete')
            sequence += 1
            begin = time.monotonic()
            record = {'sequence': sequence, 'operation': method, 'arguments': list(args),
                      'jpeg_count': len(result), 'scan_elapsed': begin - started}
            self.stage = f"SD scan: {method} {args!r} ({len(result)} JPEGs described)"
            self.scan_progress = dict(record, state='start')
            if self.scan_trace:
                self.scan_trace(self.scan_progress)
            try:
                if method == 'file_get_info':
                    value = self.describe(*args)
                else:
                    # Include iteration in the timed operation; bindings can be lazy.
                    value = list(getattr(self.camera, method)(*args))
            except Exception as exc:
                self.scan_progress = dict(record, state='error', duration=time.monotonic() - begin,
                                          error=str(exc))
                if self.scan_trace:
                    self.scan_trace(self.scan_progress)
                raise
            self.scan_progress = dict(record, state='done', duration=time.monotonic() - begin)
            if method != 'file_get_info':
                self.scan_progress['entries'] = len(value)
            if self.scan_trace:
                self.scan_trace(self.scan_progress)
            if self.scan_cancelled():
                raise RuntimeError('SD scan cancelled; baseline incomplete')
            return value

        def walk(folder):
            for name, _ in operation('folder_list_files', folder):
                if name.lower().endswith(('.jpg', '.jpeg')):
                    result.append(operation('file_get_info', folder, name))
            for name, _ in operation('folder_list_folders', folder):
                walk(posixpath.join(folder, name))
        walk('/')
        self.stage = f'SD scan complete: {len(result)} JPEGs in {time.monotonic() - started:.2f}s'
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

    def _set(self, name, value):
        widget = self.camera.get_single_config(name)
        widget.set_value(value)
        self.camera.set_single_config(name, widget)

    def _media(self):
        return str(self.camera.get_single_config('recordingmedia').get_value())

    def start_preview(self):
        # libgphoto's first Nikon capture_preview enters remote live view and
        # selects SDRAM. No still exposure is requested. Restore Card before
        # reporting ready; never allow unattended startup with SDRAM selected.
        self.stage = 'checking recording destination'
        if self._media() != 'Card':
            raise RuntimeError('Select Card recording media before enabling USB preview')
        self.preview_started = True
        try:
            self.stage = 'requesting first USB preview frame'
            # get_data_and_size borrows CameraFile storage. Keep its owner alive
            # until bytes() has copied it (including on reference-counting Python).
            camera_file = self.camera.capture_preview()
            data = bytes(camera_file.get_data_and_size())
        finally:
            self.stage = 'restoring Card recording destination'
            self._set('recordingmedia', 'Card')
        self.stage = 'verifying Card recording destination'
        if self._media() != 'Card':
            raise RuntimeError('Could not restore Card recording after starting preview')
        return data

    def preview(self):
        # Do not silently restart live view: libgphoto can select SDRAM when
        # restarting it. Hardware qualification must establish capture recovery.
        if not self.camera.get_single_config('viewfinder').get_value():
            raise RuntimeError('Camera ended live view; preview recovery needs qualification')
        if self._media() != 'Card':
            raise RuntimeError('Recording destination changed away from Card')
        camera_file = self.camera.capture_preview()
        data = bytes(camera_file.get_data_and_size())
        if self._media() != 'Card':
            raise RuntimeError('Preview changed recording destination; stop taking photos')
        return data

    def keepalive_preview(self):
        # Only called between software commands. Restarting preview uses the
        # existing Card-restore lifecycle; it never calls camera.capture().
        if time.monotonic() < self.keepalive_next_at:
            return self.preview()
        self.keepalive_next_at = time.monotonic() + 5
        if not self.camera.get_single_config('viewfinder').get_value():
            if self._media() != 'Card':
                raise RuntimeError('Recording destination changed away from Card')
            return self.start_preview()
        return self.preview()

    def close(self):
        if self.camera is not None:
            try:
                if self.preview_started:
                    try:
                        self._set('viewfinder', 0)
                    finally:
                        self._set('recordingmedia', 'Card')
                        if self._media() != 'Card':
                            raise RuntimeError('Verify recording destination on the camera')
            finally:
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

    def describe(self, folder, name):
        path = self.directory / name
        return identity('/', name, path.stat().st_size, path.stat().st_mtime_ns)

    def software_shot(self, known, destination, record, preview_enabled):
        import hashlib
        from render import validate_jpeg
        record('capture_intent', {'count': 1, 'target': 'Memory card'})
        self.shoot(1)
        path = max(self.directory.glob('*.jpg'), key=lambda p: p.stat().st_mtime_ns)
        record('capture_returned', {'folder': '/', 'name': path.name})
        item = self.describe('/', path.name)
        if key(item) in known:
            raise RuntimeError('Duplicate demo capture')
        record('identified', item)
        self.download(item, destination)
        validate_jpeg(destination)
        record('downloaded', {'sha256': hashlib.sha256(Path(destination).read_bytes()).hexdigest()})
        if preview_enabled:
            record('preview_restarted', {})
            return self.start_preview()
        return None

    def close(self):
        pass

    def start_preview(self):
        return self.preview()

    def preview(self):
        img = Image.new('RGB', (640, 426), '#416f77' if self.label == 'A' else '#bc7453')
        draw = ImageDraw.Draw(img)
        draw.text((50, 150), 'DEMO ' + self.label, fill='white', font_size=70)
        draw.text((50, 250), time.strftime('%H:%M:%S'), fill='white', font_size=32)
        buf = io.BytesIO()
        img.save(buf, 'JPEG')
        return buf.getvalue()


class CameraWorker(threading.Thread):
    def __init__(self, label, adapter, events, mode='events', poll_seconds=2, preview_fps=0,
                 baseline_required=True):
        super().__init__(name='camera-' + label, daemon=True)
        self.label, self.adapter, self.events = label, adapter, events
        self.mode, self.poll_seconds = mode, poll_seconds
        self.commands = queue.Queue()
        self.stopping = threading.Event()
        self.failure = None
        self.ready = Future()
        self.preview_fps = preview_fps
        self.frame_lock = threading.Lock()
        self.frame = None
        self.frame_at = 0
        self.frame_sequence = 0
        self.frame_times = deque(maxlen=30)
        self.cleanup_error = None
        self.baseline_required = baseline_required
        self.stage = 'not started'
        self.rejected_frame = None
        if isinstance(adapter, GPhotoCamera):
            adapter.scan_cancelled = self.stopping.is_set

    def publish_frame(self, data):
        if len(data) > 8 * 1024 * 1024:
            raise RuntimeError('Oversized camera preview')
        try:
            with Image.open(io.BytesIO(data)) as img:
                if img.format != 'JPEG':
                    raise RuntimeError('Camera preview is not JPEG')
                img.verify()
        except Exception:
            self.rejected_frame = data
            raise
        with self.frame_lock:
            self.frame, self.frame_at = data, time.monotonic()
            self.frame_sequence += 1
            self.frame_times.append(self.frame_at)

    def preview_status(self):
        with self.frame_lock:
            now = time.monotonic()
            times = [t for t in self.frame_times if now - t <= 5]
            fps = (len(times) - 1) / (times[-1] - times[0]) if len(times) > 1 else 0
            return {'frames': self.frame_sequence, 'recent_fps': round(fps, 2),
                    'frame_age_seconds': round(now - self.frame_at, 2) if self.frame_at else None,
                    'stage': getattr(self.adapter, 'stage', self.stage)}

    def latest_frame(self):
        with self.frame_lock:
            if self.failure or self.stopping.is_set() or time.monotonic() - self.frame_at > 2:
                return None
            return self.frame

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
            self.stage = 'opening camera'
            self.adapter.open()
            if self.stopping.is_set():
                raise RuntimeError('Startup cancelled')
            self.stage = 'reading SD-card baseline'
            initial = self.adapter.snapshot() if self.baseline_required else []
            if self.stopping.is_set():
                raise RuntimeError('Startup cancelled')
            observed = {key(i) for i in initial}
            if self.preview_fps:
                self.stage = 'starting preview'
                self.publish_frame(self.adapter.start_preview())
            self.stage = 'ready'
            self.ready.set_result(initial)
            next_poll = time.monotonic() + self.poll_seconds
            next_preview = time.monotonic() + 1 / self.preview_fps if self.preview_fps else float('inf')
            while not self.stopping.is_set():
                try:
                    method, args, future = self.commands.get_nowait()
                except queue.Empty:
                    future = None
                if future is not None:
                    try:
                        result = getattr(self.adapter, method)(*args)
                        if method == 'software_shot' and result is not None:
                            self.publish_frame(result)
                        future.set_result(result)
                    except Exception as exc:
                        future.set_exception(exc)
                        raise
                    continue
                if time.monotonic() >= next_preview:
                    preview_started_at = time.monotonic()
                    method = (self.adapter.keepalive_preview if self.mode == 'software' and isinstance(self.adapter, GPhotoCamera)
                              else self.adapter.preview)
                    self.publish_frame(method())
                    # Target start-to-start cadence, not a full interval added
                    # after USB transfer. Commands still run before previews.
                    next_preview = preview_started_at + 1 / self.preview_fps
                if self.mode == 'events':
                    item = self.adapter.event()
                    if item:
                        self.events.put((self.label, item, None))
                elif self.mode == 'poll' and time.monotonic() >= next_poll:
                    items = self.adapter.snapshot()
                    for item in items:
                        if key(item) not in observed:
                            self.events.put((self.label, item, None))
                    observed = {key(i) for i in items}
                    next_poll = time.monotonic() + self.poll_seconds
                else:
                    self.stopping.wait(min(0.05, max(0.005, next_preview - time.monotonic())))
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
            except Exception as exc:
                self.cleanup_error = 'Camera cleanup failed: ' + str(exc)
                self.failure = self.failure or self.cleanup_error
                self.events.put((self.label, None, self.cleanup_error))
