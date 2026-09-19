"""One coordinator owns batch state; camera threads own their USB sessions."""
import copy
import json
import logging
import queue
import threading
import time
import uuid
from concurrent.futures import Future
from pathlib import Path
from camera import CameraWorker, key, ordered
from printer import Printer
from qualification import validate_software_printing
from render import normalize_overlay, render_sheet, validate_jpeg, validate_layout
from storage import atomic_bytes, save_json
from software import SoftwareWorkflow
from recovery import CameraRecovery
from config import validate_preview_fps
from gallery import Gallery
from display_settings import DisplaySettings
from operator_tools import OperatorTools
from calibration_print import CalibrationPrint
from scan_alignment import ScanAlignment

LOG = logging.getLogger(__name__)


class Engine(OperatorTools, DisplaySettings, CameraRecovery, SoftwareWorkflow):
    def __init__(self, config, adapters):
        self.config = config
        self.instance_id = uuid.uuid4().hex
        self.application_control = None
        self.software = config['camera_mode'] == 'software'
        if self.software:
            validate_software_printing(config['printer'], config['demo'])
        self.capture_futures = []
        self.reconnect_queue = []
        self.reconnect_label = None
        self.reconnect_next_at = time.monotonic() + 10
        self.root = Path(config['data_dir'])
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'state.json'
        self.preview_settings_path = self.root / 'operator-preview.json'
        if self.preview_settings_path.exists():
            saved = json.loads(self.preview_settings_path.read_text())
            validate_preview_fps(saved['fps'], allow_disabled=False)
            self.config['preview_fps'] = saved['fps']
        self.layout_path = self.root / 'operator-layout.json'
        self.layout = (json.loads(self.layout_path.read_text()) if self.layout_path.exists()
                       else copy.deepcopy(config['layout']))
        validate_layout(self.layout)
        self.initialize_display()
        self.initialize_operator_tools()
        self.gallery = Gallery(self.root)
        self.calibration_print = CalibrationPrint(self)
        self.scan_alignment = ScanAlignment(self)
        self.started_at = time.monotonic()
        self.lock = threading.RLock()
        self.events, self.commands = queue.Queue(), queue.Queue()
        self.stop_event = threading.Event()
        self.workers = {c: CameraWorker(c, adapters[c], self.events, config['camera_mode'],
                                       config['poll_seconds'], config.get('preview_fps', 0),
                                       baseline_required=not self.software) for c in ('A', 'B')}
        self.printer = Printer(config['printer'])
        self.phase, self.error = 'starting', None
        self.camera_status = {c: 'connecting' for c in ('A', 'B')}
        self.binding = {'demo': config['demo'], 'cameras': config.get('cameras', {})}
        if self.software:
            self.binding['capture_mode'] = 'software'
        self.state = self._load()
        self.thread = threading.Thread(target=self.run, name='coordinator', daemon=True)

    def _load(self):
        if not self.path.exists():
            return {'version': 1, 'binding': self.binding, 'initialized': False,
                    'seen': {'A': [], 'B': []}, 'pending': {'A': [], 'B': []},
                    'current': None, 'last': None}
        state = json.loads(self.path.read_text())  # Never replace corrupt state with a fresh baseline.
        if state['version'] != 1 or state['binding'] != self.binding:
            raise ValueError('State belongs to different cameras/mode; use a separate data directory')
        if type(state['initialized']) is not bool:
            raise ValueError('Invalid saved state')
        for c in ('A', 'B'):
            if not isinstance(state['seen'][c], list) or not isinstance(state['pending'][c], list):
                raise ValueError('Invalid saved camera state')
            if any(key(i) not in state['seen'][c] for i in state['pending'][c]):
                raise ValueError('Pending files are missing from saved observations')
        current = state['current']
        if current and current['stage'] not in ('preparing', 'print_intent', 'print_uncertain', 'capturing', 'capture_held'):
            raise ValueError('Unknown saved batch stage')
        if current and self.software:
            if not current.get('software') or any(
                not isinstance(current.get('shots', {}).get(c), list) or len(current['shots'][c]) != 8
                or any(not isinstance(s, dict) for s in current['shots'][c]) for c in ('A', 'B')
            ):
                raise ValueError('Invalid saved software shutter records; preserve state for investigation')
        return state

    def save(self):
        save_json(self.path, self.state)

    def start(self):
        for worker in self.workers.values():
            worker.start()
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        # Let an in-flight batch reach a durable boundary before ending workers.
        if self.thread.ident is not None:
            self.thread.join(timeout=55)
        for worker in self.workers.values():
            worker.stopping.set()
        for worker in self.workers.values():
            if worker.ident is not None:
                worker.join(timeout=2)

    def status(self):
        with self.lock:
            return {'phase': self.phase, 'error': self.error,
                    'instance_id': self.instance_id,
                    'application_control_available': bool(self.application_control and self.application_control.available()),
                    'application_control_action': self.application_control.action if self.application_control else None,
                    'slideshow': copy.deepcopy(self.display),
                    'calibration': {'strip_offsets_px':list(self.config['printer'].get('strip_offsets_px',[0]*4)), 'sheet_offset_y_px':self.config['printer'].get('sheet_offset_y_px',0)},
                    'data_dir': str(self.root),
                    'countdown_seconds':self.countdown_seconds,
                    'preview_fps': self.config.get('preview_fps', 0),
                    'layout': copy.deepcopy(self.layout),
                    'overlay_settings': copy.deepcopy(self.overlay_settings),
                    'uptime_seconds': int(time.monotonic() - self.started_at),
                    'cameras': dict(self.camera_status),
                    'previews': {c: w.preview_status() for c, w in self.workers.items()},
                    'capture_mode': self.config['camera_mode'],
                    'capture_busy': any(not f.done() for f in self.capture_futures),
                    'reconnect_available': self.reconnect_available(),
                    'counts': {c: (sum(bool(s.get('downloaded_at')) for s in self.state['current']['shots'][c])
                                   if self.software and self.state['current'] else len(self.state['pending'][c]))
                               for c in ('A', 'B')},
                    'current': copy.deepcopy(self.state['current']),
                    'last': ({**copy.deepcopy(self.state['last']),
                              'preview_available': (self.root / 'batches' / self.state['last']['id'] / 'preview.jpg').is_file()}
                             if self.state['last'] else None),
                    'printing_change_available': (self.software and not self.config['demo']
                        and self.phase == 'watching' and not self.state['current']
                        and not any(not f.done() for f in self.capture_futures)),
                    'demo': self.config['demo'], 'printing_enabled': self.config['printer']['enabled']}

    def request(self, action, *args):
        future = Future()
        if self.stop_event.is_set() or not self.thread.is_alive():
            future.set_exception(RuntimeError('Coordinator is stopped; inspect logs and restart'))
        else:
            self.commands.put((action, args, future))
        return future

    def ingest(self, camera, item):
        if self.software:
            return  # External events never enter a software-triggered batch.
        ident = key(item)
        if ident in self.state['seen'][camera]:
            return
        self.state['seen'][camera].append(ident)
        self.state['pending'][camera].append(item)
        self.save()

    def initialize(self):
        snapshots = {c: w.ready.result(timeout=120) for c, w in self.workers.items()}
        if self.software:
            self.software_initialize()
            return
        with self.lock:
            if not self.state['initialized']:
                self.state['seen'] = {c: [key(i) for i in snapshots[c]] for c in ('A', 'B')}
                self.state['initialized'] = True
                self.save()
            else:
                # Missing referenced files mean a removed/replaced card or manual deletion.
                # Stop rather than silently pair a different set of images.
                for c in ('A', 'B'):
                    present = {key(i) for i in snapshots[c]}
                    needed = list(self.state['pending'][c])
                    if self.state['current'] and self.state['current']['stage'] == 'preparing':
                        needed += self.state['current']['files'][c]
                    if any(key(i) not in present for i in needed):
                        raise RuntimeError(f'Camera {c} is missing saved batch files; restore its SD card')
                    if self.state['seen'][c] and not present.intersection(self.state['seen'][c]):
                        raise RuntimeError(f'Camera {c} SD baseline changed; use a new data directory for a new card')
                    for item in ordered(snapshots[c]):
                        self.ingest(c, item)
            self.camera_status = {c: 'connected' for c in ('A', 'B')}
            current = self.state['current']
            if current and current['stage'] in ('print_intent', 'print_uncertain'):
                current['stage'] = 'print_uncertain'
                self.save()
                self.phase = 'print_uncertain'
                self.error = 'A print may already exist. Check CUPS and the printer, then acknowledge. No automatic retry.'
            else:
                self.phase = 'watching'

    def freeze(self, software=False):
        with self.lock:
            batch_id = 'batch-' + uuid.uuid4().hex
            directory = self.root / 'batches' / batch_id
            directory.mkdir(parents=True)
            overlays = []
            for index in range(1, 5):
                source = self.root / 'overlays' / f'strip{index}.png'
                if source.exists():
                    destination = directory / f'overlay{index}.png'
                    atomic_bytes(destination, source.read_bytes())
                    overlays.append(destination.name)
                else:
                    overlays.append(None)
            self.state['current'] = {
                'id': batch_id, 'stage': 'preparing', 'created_at': time.time(),
                'files': {c: self.state['pending'][c][:8] for c in ('A', 'B')},
                'countdown_seconds':self.countdown_seconds,
                'layout': copy.deepcopy(self.layout),
                'overlay_settings': copy.deepcopy(self.overlay_settings),
                'printer': copy.deepcopy(self.config['printer']), 'overlays': overlays,
            }
            if software:
                self.state['current'].update(stage='capturing', software=True,
                                             shots={c: [{} for _ in range(8)] for c in ('A', 'B')})
            for c in ('A', 'B'):
                self.state['pending'][c] = self.state['pending'][c][8:]
            self.save()
            save_json(directory / 'manifest.json', self.state['current'])

    def process(self):
        with self.lock:
            batch = copy.deepcopy(self.state['current'])
            self.phase = 'downloading'
        if batch.get('software') and batch['printer']['enabled']:
            # A saved live batch cannot override a currently disabled appliance.
            try:
                if not self.config['printer']['enabled']:
                    raise ValueError('Current printing configuration is disabled')
                validate_software_printing(self.config['printer'], self.config['demo'])
                validate_software_printing(batch['printer'], self.config['demo'])
            except ValueError as exc:
                raise RuntimeError('Saved software batch cannot enable physical printing: ' + str(exc)) from exc
        directory = self.root / 'batches' / batch['id']
        photos = {c: [] for c in ('A', 'B')}
        downloads = []
        for c in ('A', 'B'):
            for index, item in enumerate(batch['files'][c], 1):
                path = directory / f'{c}{index:02d}.jpg'
                photos[c].append(path)
                if batch.get('software'):
                    actual = self.workers[c].request('describe', item['folder'], item['name']).result(30)
                    if actual != item:
                        raise RuntimeError('Captured card file changed before rendering')
                    if self.software_local_valid(batch['shots'][c][index - 1], path):
                        continue
                # Restart/retry of preparation is safe; no printing has been attempted.
                downloads.append((self.workers[c].request('download', item, path), path))
        for future, path in downloads:
            future.result(timeout=120)
            validate_jpeg(path)
        with self.lock:
            self.phase = 'rendering'
        overlays = [directory / p if p else None for p in batch['overlays']]
        sheet = directory / 'sheet.png'
        render_sheet(photos, overlays, batch['layout'], sheet,
                     strip_offsets_px=batch['printer'].get('strip_offsets_px', [0, 0, 0, 0]),
                     sheet_offset_y_px=batch['printer'].get('sheet_offset_y_px',0),
                     overlay_settings=batch.get('overlay_settings'))
        with self.lock:
            if any(w.failure for w in self.workers.values()):
                raise RuntimeError('Camera failed during preparation; restart after checking connections')
            self.phase = 'submitting'
            # Persist intent BEFORE calling lp. A crash after here must never resubmit.
            self.state['current']['stage'] = 'print_intent'
            self.save()
        try:
            result = Printer(batch['printer']).submit(sheet, batch['id'])
        except Exception as exc:
            with self.lock:
                self.state['current']['stage'] = 'print_uncertain'
                self.state['current']['error'] = str(exc)
                self.save()
                self.phase, self.error = 'print_uncertain', str(exc)
            return
        with self.lock:
            completed = {**batch, **result, 'stage': 'complete', 'completed_at': time.time()}
            self.state['last'] = completed
            self.state['current'] = None
            self.save()
            save_json(directory / 'manifest.json', completed)
            self.phase, self.error = 'watching', None

    def action(self, action, *args):
        if action == 'application_control':
            if not self.application_control: raise ValueError('Application controls are unavailable in this preview')
            return self.application_control.request(args[0])
        if action == 'scan_prepare': return self.calibration_print.prepare(scan=True)
        if action == 'scan_upload': return self.scan_alignment.upload(*args)
        if action == 'scan_propose': return self.scan_alignment.propose(args[0])
        if action == 'scan_apply': return self.scan_alignment.apply(args[0])
        if action == 'overlay_settings': return self.save_overlay_settings(args[0])
        if action == 'calibration_prepare': return self.calibration_print.prepare()
        if action == 'calibration_print': return self.calibration_print.print_once(args[0]['id'])
        if action == 'calibration_measure': return self.calibration_print.measure(args[0])
        if action == 'calibration_acknowledge': return self.calibration_print.acknowledge(args[0]['id'])
        if action == 'printing_settings':
            return self.set_printing(args[0])
        if action == 'dry_run':
            return self.render_dry_run()
        if action == 'slideshow_settings':
            return self.save_display(args[0])
        if action == 'calibration':
            return self.apply_calibration(args[0])
        if action == 'session_settings':
            return self.save_session(args[0])
        if action == 'reconnect':
            return self.begin_reconnect()
        if action in ('capture', 'resume_capture', 'abandon_capture'):
            if not self.software:
                raise ValueError('Select software capture mode first')
            return self.software_action(action)
        if action == 'preview_settings':
            candidate = args[0]
            if not isinstance(candidate, dict) or set(candidate) != {'fps'}:
                raise ValueError('Preview settings need fps')
            validate_preview_fps(candidate['fps'], allow_disabled=False)
            if (self.phase != 'watching' or self.state['current']
                    or not self.config.get('preview_fps')
                    or any(w.failure for w in self.workers.values())):
                raise ValueError('Change preview speed only while cameras are ready, previews enabled, and no batch is active')
            with self.lock:
                save_json(self.preview_settings_path, candidate)
                self.config['preview_fps'] = candidate['fps']
                for worker in self.workers.values():
                    worker.preview_fps = candidate['fps']
            return
        if action == 'layout':
            candidate = copy.deepcopy(args[0])
            validate_layout(candidate)
            with self.lock:
                save_json(self.layout_path, candidate)
                self.layout = candidate
        elif action == 'overlay':
            index, content = args
            if index not in (1, 2, 3, 4):
                raise ValueError('Invalid strip number')
            atomic_bytes(self.root / 'overlays' / f'strip{index}.png', normalize_overlay(content))
        elif action == 'reset':
            if self.state['current'] or self.phase != 'watching':
                raise ValueError('Reset is available only while watching with no active batch')
            if self.software:
                return  # No pending external photographs and no historical scan.
            futures = {c: w.request('snapshot') for c, w in self.workers.items()}
            snapshots = {c: f.result(timeout=120) for c, f in futures.items()}
            with self.lock:
                for c in ('A', 'B'):
                    # Keep prior observations to ignore queued old events.
                    self.state['seen'][c] = list(set(self.state['seen'][c]) | {key(i) for i in snapshots[c]})
                    self.state['pending'][c] = []
                self.save()
        elif action == 'acknowledge':
            with self.lock:
                if self.phase != 'print_uncertain':
                    raise ValueError('There is no uncertain print to acknowledge')
                completed = {**self.state['current'], 'stage': 'complete',
                             'status': 'acknowledged_without_retry', 'completed_at': time.time()}
                self.state['last'], self.state['current'] = completed, None
                self.save()
                save_json(self.root / 'batches' / completed['id'] / 'manifest.json', completed)
                self.phase, self.error = 'watching', None
        elif action == 'retry':
            if self.phase != 'error' or not self.state['current'] or self.state['current']['stage'] != 'preparing':
                raise ValueError('Only a failed preparation can be retried')
            if any(w.failure for w in self.workers.values()):
                raise ValueError('A camera worker failed; check its connection and restart Stripshot')
            self.phase, self.error = 'watching', None
        elif action == 'demo':
            if self.software or not self.config['demo'] or self.phase != 'watching' or self.state['current']:
                raise ValueError('Demo capture is available only while the demo is watching')
            futures = [w.request('shoot') for w in self.workers.values()]
            for future in futures:
                future.result(timeout=30)
        else:
            raise ValueError('Unknown action')

    def run(self):
        try:
            self.initialize()
            while not self.stop_event.is_set():
                # A failed camera holds the whole appliance; its partner cannot print alone.
                if any(w.failure for w in self.workers.values()) and self.phase not in ('print_uncertain', 'capture_held', 'reconnecting'):
                    with self.lock:
                        if self.software and self.state['current'] and self.state['current']['stage'] == 'capturing':
                            self.state['current']['stage'] = 'capture_held'
                            self.save()
                            self.phase = 'capture_held'
                        else:
                            self.phase = 'error'
                        self.error = 'Camera connection failed. Check connections and restart Stripshot.'
                        for c, w in self.workers.items():
                            if w.failure:
                                self.camera_status[c] = w.failure
                if (self.config.get('auto_reconnect', True) and not self.state['current']
                        and time.monotonic() >= self.reconnect_next_at and self.reconnect_available()):
                    self.begin_reconnect()
                if self.phase == 'reconnecting':
                    self.reconnect_step()
                try:
                    action, args, future = self.commands.get_nowait()
                except queue.Empty:
                    future = None
                if future is not None:
                    try:
                        result = self.action(action, *args)
                        future.set_result(True if result is None else result)
                    except Exception as exc:
                        future.set_exception(exc)
                try:
                    c, item, error = self.events.get(timeout=0.05)
                    with self.lock:
                        if error:
                            self.camera_status[c] = error
                        elif item:
                            self.ingest(c, item)
                except queue.Empty:
                    pass
                if self.phase == 'capturing':
                    self.software_step()
                if self.phase == 'watching':
                    try:
                        if not self.state['current'] and all(len(self.state['pending'][c]) >= 8 for c in ('A', 'B')):
                            self.freeze()
                        if self.state['current']:
                            self.process()
                    except Exception as exc:
                        LOG.exception('Batch preparation failed')
                        with self.lock:
                            self.phase, self.error = 'error', str(exc)
        except Exception as exc:
            LOG.exception('Coordinator stopped')
            with self.lock:
                self.phase, self.error = 'error', str(exc)
        finally:
            while True:
                try:
                    _, _, future = self.commands.get_nowait()
                    future.set_exception(RuntimeError('Coordinator stopped; inspect logs and restart'))
                except queue.Empty:
                    break
