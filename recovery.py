"""Serial-verified camera reconnection. Never retry a shutter or batch here."""
import time
from camera import CameraWorker, GPhotoCamera


class CameraRecovery:
    def reconnect_available(self):
        failed = [w for w in self.workers.values() if w.failure]
        return (self.software and self.thread.is_alive()
                and self.phase in ('error', 'capture_held') and bool(failed)
                and all(w.ready.done() for w in self.workers.values())
                and all(not w.is_alive() and not w.cleanup_error for w in failed)
                and all(f.done() for f in self.capture_futures))

    def begin_reconnect(self):
        if not self.reconnect_available():
            raise ValueError('Cannot reconnect while a camera call/cleanup is running or USB release is unconfirmed. Check the camera details and existing terminal; keep any held batch for review')
        self.reconnect_queue = [c for c, w in self.workers.items() if w.failure]
        self.reconnect_label = None
        self.phase, self.error = 'reconnecting', None

    def reconnected_adapter(self, old):
        if isinstance(old.adapter, GPhotoCamera):
            excluded = [w.adapter.port for w in self.workers.values()
                        if w is not old and isinstance(w.adapter, GPhotoCamera)
                        and (not w.failure or w.is_alive())]
            return GPhotoCamera(None, old.adapter.serial, excluded_ports=excluded)
        return old.adapter  # Simulated cameras only; no native handle to reuse.

    def reconnect_step(self):
        if self.reconnect_label is not None:
            worker = self.workers[self.reconnect_label]
            if not worker.ready.done():
                if time.monotonic() >= self.reconnect_deadline:
                    self.phase, self.error = 'error', 'Camera reconnect timed out. The owning worker is still reserved; check connections and restart. No shutter was issued.'
                return  # Do not replace a worker stuck in a native call.
            try:
                worker.ready.result()
            except Exception as exc:
                self.reconnect_next_at = time.monotonic() + 30
                self.phase = 'capture_held' if self.state['current'] and self.state['current']['stage'] == 'capture_held' else 'error'
                self.error = 'Reconnect failed: ' + str(exc)
                self.reconnect_queue = []
                self.reconnect_label = None
                return
            self.camera_status[self.reconnect_label] = 'connected'
            self.reconnect_label = None
        if self.reconnect_queue:
            label = self.reconnect_queue.pop(0)
            old = self.workers[label]
            worker = CameraWorker(label, self.reconnected_adapter(old), self.events,
                                  'software', self.config['poll_seconds'], self.config.get('preview_fps', 0),
                                  baseline_required=False)
            with self.lock:
                self.workers[label] = worker
                self.reconnect_label = label
                self.reconnect_deadline = time.monotonic() + 120
                self.camera_status[label] = 'reconnecting by serial'
            worker.start()
            return
        self.reconnect_next_at = time.monotonic() + 10
        current = self.state['current']
        if current:
            self.phase = 'capture_held' if current['stage'] == 'capture_held' else 'error'
            self.error = 'Cameras reconnected. Review the held batch before explicit resume/retry; no photos were taken.'
        else:
            self.phase, self.error = 'watching', None
