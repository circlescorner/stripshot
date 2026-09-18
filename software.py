"""Durable software-shutter batches. No card scans or automatic shutter retries."""
import hashlib
import time

from camera import key
from render import validate_jpeg
from storage import save_json


class SoftwareWorkflow:
    def software_record(self, camera, index, event, data):
        # Called by the camera's owning thread. Save/ fsync finishes before
        # camera.capture is allowed to run. Both cameras serialize state writes.
        with self.lock:
            batch = self.state['current']
            shot = batch['shots'][camera][index]
            if event == 'capture_intent':
                if self.stop_event.is_set() or batch['stage'] != 'capturing' or shot:
                    raise RuntimeError('Shutter refused: stopped, held, or intent already exists')
                shot.update(intent_at=time.time(), intent=data)
            elif event == 'capture_returned':
                shot['returned'] = data
                shot['returned_at'] = time.time()
            elif event == 'identified':
                if key(data) in self.state['seen'][camera]:
                    raise RuntimeError('Returned identity was already assigned; no replacement shot')
                shot['identity'] = data
                self.state['seen'][camera].append(key(data))
            elif event == 'downloaded':
                shot.update(data, downloaded_at=time.time())
            elif event == 'preview_restarted':
                shot['preview_restarted_at'] = time.time()
            else:
                raise ValueError('Unknown shutter record')
            self.save()

    def software_initialize(self):
        # The workers have opened serial-verified sessions, but made no inventory.
        with self.lock:
            self.state['initialized'] = True
            current = self.state['current']
            if current and current['stage'] in ('capturing', 'capture_held'):
                current['stage'] = 'capture_held'
                self.phase = 'capture_held'
                self.error = 'Interrupted capture. Review saved shots; resume only known files and unissued slots, or abandon this batch.'
            elif current and current['stage'] in ('print_intent', 'print_uncertain'):
                current['stage'] = 'print_uncertain'
                self.phase = 'print_uncertain'
                self.error = 'Saved print intent requires acknowledgment; no automatic submission.'
            else:
                self.phase = 'watching'
            self.camera_status = {c: 'connected' for c in ('A', 'B')}
            self.save()

    def software_action(self, action):
        if action == 'capture':
            if self.phase != 'watching' or self.state['current']:
                raise ValueError('A batch is already active or the cameras are not ready')
            if any(w.failure for w in self.workers.values()):
                raise ValueError('Restart after checking camera connections')
            self.freeze(software=True)
            self.phase, self.error = 'capturing', None
        elif action in ('resume_capture', 'abandon_capture'):
            if self.phase != 'capture_held':
                raise ValueError('No held capture batch')
            if any(not f.done() for f in self.capture_futures):
                raise ValueError('A camera operation is still running; wait for it to finish')
            batch = self.state['current']
            if action == 'resume_capture':
                if any(w.failure for w in self.workers.values()):
                    raise ValueError('Reconnect the cameras or restart before resuming')
                for shots in batch['shots'].values():
                    for shot in shots:
                        if shot and 'identity' not in shot:
                            raise ValueError('Uncertain shutter or unidentified returned file: cannot resume or replace. Preserve evidence and abandon this batch after review.')
                # Return to capture steps; each known identity is rechecked and
                # downloaded if necessary, never recaptured.
                with self.lock:
                    batch['stage'] = 'capturing'
                    self.save()
                    self.phase, self.error = 'capturing', None
            else:
                with self.lock:
                    archived = {**batch, 'stage': 'abandoned', 'abandoned_at': time.time()}
                    # Preserve the full record BEFORE releasing the active batch.
                    save_json(self.root / 'batches' / batch['id'] / 'manifest.json', archived)
                    self.state['current'] = None
                    self.save()
                    self.phase, self.error = 'watching', None
        else:
            raise ValueError('Unknown software capture action')

    def software_local_valid(self, shot, path):
        if not path.is_file() or not shot.get('sha256'):
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != shot['sha256']:
            return False
        validate_jpeg(path)
        return True

    def software_step(self):
        """One paired round; return to coordinator between rounds for status/actions."""
        batch = self.state['current']
        directory = self.root / 'batches' / batch['id']
        self.capture_futures = []
        try:
            # Resume existing identities without issuing a shutter. Verify exact
            # metadata even when the local download is already durable.
            index = next((i for i in range(8) if any(
                not batch['shots'][c][i].get('settled') for c in ('A', 'B'))), None)
            if index is None:
                for c in ('A', 'B'):
                    files = [s['identity'] for s in batch['shots'][c]]
                    if len({key(i) for i in files}) != 8:
                        raise RuntimeError('Expected eight unique exact identities per camera')
                    for item in files:
                        actual = self.workers[c].request('describe', item['folder'], item['name']).result(30)
                        if actual != item:
                            raise RuntimeError('Captured card file changed; batch held')
                with self.lock:
                    batch['files'] = {c: [s['identity'] for s in batch['shots'][c]] for c in ('A', 'B')}
                    batch['stage'] = 'preparing'
                    self.save()
                    save_json(directory / 'manifest.json', batch)
                    self.phase = 'watching'
                return
            round_started = time.monotonic()
            sequences = {c: w.frame_sequence for c, w in self.workers.items()}
            for c in ('A', 'B'):
                shot = batch['shots'][c][index]
                path = directory / f'{c}{index + 1:02d}.jpg'
                if shot:
                    if 'identity' not in shot:
                        raise RuntimeError('Uncertain shutter outcome; no replacement capture')
                    item = shot['identity']
                    actual = self.workers[c].request('describe', item['folder'], item['name']).result(30)
                    if actual != item:
                        raise RuntimeError('Saved file identity changed; cannot reconcile')
                    if not self.software_local_valid(shot, path):
                        self.workers[c].request('download', item, path).result(120)
                        validate_jpeg(path)
                        self.software_record(c, index, 'downloaded', {
                            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
                else:
                    callback = lambda e, d, c=c, i=index: self.software_record(c, i, e, d)
                    future = self.workers[c].request('software_shot', set(self.state['seen'][c]),
                                                     path, callback, bool(self.config.get('preview_fps')))
                    self.capture_futures.append(future)
            # Dispatch A and B before waiting; no strict shutter synchronization
            # is claimed. Durable timestamps measure their real timing.
            for future in self.capture_futures:
                future.result(120)
            if self.config.get('preview_fps'):
                # Allow two fresh frames after the returned startup frame.
                targets = {c: w.frame_sequence + 2 for c, w in self.workers.items()}
                deadline = time.monotonic() + 3
                while not all(w.frame_sequence >= targets[c] for c, w in self.workers.items()):
                    if self.stop_event.wait(.05):
                        raise RuntimeError('Stopped between shots')
                    if any(w.failure for w in self.workers.values()) or time.monotonic() >= deadline:
                        raise RuntimeError('Preview recovery did not supply two frames within three seconds')
            with self.lock:
                for c in ('A', 'B'):
                    shot = batch['shots'][c][index]
                    shot['settled'] = True
                    shot['preview_frames'] = self.workers[c].frame_sequence - sequences[c]
                    shot['round_seconds'] = time.monotonic() - round_started
                self.save()
        except Exception as exc:
            with self.lock:
                batch['stage'] = 'capture_held'
                batch['capture_error'] = str(exc)
                self.save()
                self.phase, self.error = 'capture_held', str(exc)
