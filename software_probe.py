"""Explicitly selected hardware diagnostic; not used by the appliance."""
from pathlib import PurePosixPath
from camera import GPhotoCamera, key
from render import validate_jpeg


class SoftwareProbeCamera(GPhotoCamera):
    def _fresh_inventory(self):
        self.stage = 'reopening session to verify SD persistence'
        self.close()
        self.camera = None
        self.preview_started = False
        if self.scan_cancelled():
            raise RuntimeError('Probe cancelled after capture')
        self.open()
        final = self.snapshot()
        return final

    def software_probe(self, baseline, destination, record):
        captured = self._capture_once(record)
        final = self._fresh_inventory()
        known = {key(i) for i in baseline}
        new = [i for i in final if key(i) not in known]
        record('new_card_jpegs', new)
        if len(new) != 1:
            raise RuntimeError(f'Expected exactly one new card JPEG; found {len(new)}; no retry')
        item = new[0]
        # RAW+JPEG can return the RAW path; require the matching stem and folder.
        if item['folder'] != captured['folder'] or PurePosixPath(item['name']).stem != PurePosixPath(captured['name']).stem:
            raise RuntimeError('New JPEG does not match returned capture path')
        self.stage = 'downloading verified software capture'
        self.download(item, destination)
        validate_jpeg(destination)
        record('download_verified', {'identity': item, 'path': str(destination)})
        if self.scan_cancelled():
            raise RuntimeError('Probe cancelled before preview restart')
        frame = self.start_preview()
        record('preview_restarted', {'jpeg_bytes': len(frame)})
        return frame

    def cycle_shot(self, known, destination, record):
        """One shot with prompt preview recovery; fresh-session audit follows cycle."""
        captured = self._capture_once(record)
        if not captured['name'].lower().endswith(('.jpg', '.jpeg')):
            raise RuntimeError('Cycle requires a returned JPEG path; no further shots issued')
        self.stage = 'identifying cycle JPEG'
        item = self.describe(captured['folder'], captured['name'])
        if key(item) in {key(i) for i in known}:
            raise RuntimeError('Capture returned an already known file; no retry')
        self.stage = 'downloading cycle JPEG'
        self.download(item, destination)
        validate_jpeg(destination)
        record('download_verified', {'identity': item, 'path': str(destination)})
        if self.scan_cancelled():
            raise RuntimeError('Cycle cancelled before preview restart')
        frame = self.start_preview()
        record('preview_restarted', {'jpeg_bytes': len(frame)})
        return item, frame

    def verify_cycle(self, baseline, captured, record, full_audit=True):
        if not full_audit:
            if len(captured) != 8 or len({key(i) for i in captured}) != 8:
                raise RuntimeError('Expected eight unique downloaded JPEG identities')
            for item in captured:
                if self.scan_cancelled():
                    raise RuntimeError('Cycle verification cancelled')
                if self.describe(item['folder'], item['name']) != item:
                    raise RuntimeError('Captured file identity changed')
            # Each exact returned file was already downloaded and decoded.
            # This is not a fresh-session inventory of unrelated card contents.
            record('exact_eight_downloads_verified', captured)
            return self.preview()
        final = self._fresh_inventory()
        known = {key(i) for i in baseline}
        new = [i for i in final if key(i) not in known]
        record('new_card_jpegs', new)
        expected = {key(i) for i in captured}
        if len(captured) != 8 or len(expected) != 8 or len(new) != 8 or {key(i) for i in new} != expected:
            raise RuntimeError('Fresh card inventory does not match the exact eight downloaded JPEGs')
        record('exact_eight_verified', captured)
        if self.scan_cancelled():
            raise RuntimeError('Cycle cancelled before preview restart')
        return self.start_preview()
