"""Read only completed local batches; never enumerate camera cards."""
import io
import json
import re
import threading
import time
from pathlib import Path
from PIL import Image, ImageOps
from storage import atomic_bytes

BATCH_ID = re.compile(r'batch-[0-9a-f]{32}\Z')
PHOTO_NAME = re.compile(r'[AB]0[1-8]\.jpg\Z')


class Gallery:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.Lock()
        self.next_refresh = 0
        self.entries = []

    def catalog(self, source='all'):
        with self.lock:
            if time.monotonic() >= self.next_refresh:
                entries = []
                for path in (self.root / 'batches').glob('batch-*/manifest.json'):
                    if not BATCH_ID.fullmatch(path.parent.name):
                        continue
                    try:
                        batch = json.loads(path.read_text())
                        if not isinstance(batch,dict):
                            continue
                        if batch.get('stage') != 'complete' or batch.get('id') != path.parent.name:
                            continue
                        completed = float(batch.get('completed_at', 0))
                        for n in range(1,9):
                            for camera in ('A','B'):
                                name = f'{camera}{n:02d}.jpg'
                                if (path.parent / name).is_file():
                                    entries.append({'id': path.parent.name + '/' + name,
                                                    'url': '/slideshow/photos/' + path.parent.name + '/' + name,
                                                    'batch_id':path.parent.name, 'completed_at':completed})
                        if (path.parent / 'sheet.png').is_file():
                            entries.append({'id':path.parent.name + '/sheet.png',
                                            'url':'/slideshow/photos/' + path.parent.name + '/sheet.png',
                                            'batch_id':path.parent.name, 'completed_at':completed})
                    except (OSError, ValueError, TypeError):
                        continue
                self.entries = sorted(entries, key=lambda e:(e['completed_at'],e['batch_id']))
                self.next_refresh = time.monotonic() + 10
            entries = self.entries
            if source == 'sheets':
                return [dict(e) for e in entries if e['id'].endswith('/sheet.png')]
            photos = [e for e in entries if not e['id'].endswith('/sheet.png')]
            if source == 'latest' and photos:
                latest = photos[-1]['batch_id']
                photos = [e for e in photos if e['batch_id'] == latest]
            return [dict(e) for e in photos]

    def original(self, batch_id, name):
        if not BATCH_ID.fullmatch(batch_id) or not (PHOTO_NAME.fullmatch(name) or name == 'sheet.png'):
            raise FileNotFoundError('Unknown gallery image')
        allowed = self.catalog('sheets' if name == 'sheet.png' else 'all')
        if not any(e['id'] == batch_id + '/' + name for e in allowed):
            raise FileNotFoundError('Not a completed gallery image')
        return self.root / 'batches' / batch_id / name

    def image(self, batch_id, name):
        original = self.original(batch_id, name)
        # Browser-sized derived file; retain the untouched full original.
        stat = original.stat()
        cache = self.root / 'gallery-cache' / batch_id / f'{name}-{stat.st_size}-{stat.st_mtime_ns}.jpg'
        with self.lock:
            if not cache.exists():
                with Image.open(original) as im:
                    im.seek(0)
                    image = ImageOps.exif_transpose(im).convert('RGB')
                    image.thumbnail((1920,1920), Image.Resampling.LANCZOS)
                    data = io.BytesIO(); image.save(data,'JPEG',quality=90)
                atomic_bytes(cache,data.getvalue())
        return cache
