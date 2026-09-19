"""Read only completed local batches; never enumerate camera cards."""
import hashlib
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
        self.thumbnail_lock = threading.Lock()
        self.display_lock = threading.Lock()
        self.next_refresh = 0
        self.entries = []
        self.allowed = set()

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
                self.allowed = {e['id'] for e in self.entries}
                self.next_refresh = time.monotonic() + 10
            if source == 'index':
                return None
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
        self.catalog('index')
        if batch_id + '/' + name not in self.allowed:
            raise FileNotFoundError('Not a completed gallery image')
        return self.root / 'batches' / batch_id / name

    @staticmethod
    def describe(entry):
        item = dict(entry)
        name = item['id'].split('/')[-1]
        item.update(thumbnail=item['url'] + '?size=thumb',
                    original='/photos/' + item['id'],
                    caption='Finished four-strip sheet' if name == 'sheet.png' else
                            f'Camera {name[0]} · Photo {int(name[1:3])}')
        return item

    def window(self, settings, current='', move=0, seed=''):
        entries = self.catalog(settings['source'])
        if settings['shuffle_all']:
            # Stable hash order: arriving sessions do not reshuffle existing history.
            entries.sort(key=lambda e: hashlib.sha256((seed + e['id']).encode()).digest())
        index = next((i for i, e in enumerate(entries) if e['id'] == current), 0)
        if entries and current and any(e['id'] == current for e in entries):
            index = (index + move) % len(entries)
        return {'settings': settings, 'total': len(entries), 'index': index,
                'photo': self.describe(entries[index]) if entries else None,
                'neighbors': [self.describe(entries[(index+d) % len(entries)]) for d in (1,-1)] if len(entries)>1 else []}

    def page(self, page=1, source='all', per_page=3):
        entries = self.catalog('all') + self.catalog('sheets')
        batches = {}
        for item in sorted(entries, key=lambda e: (e['completed_at'], e['batch_id']), reverse=True):
            batches.setdefault(item['batch_id'], []).append(self.describe(item))
        if source == 'sheets':
            batches = {key: [e for e in values if e['id'].endswith('/sheet.png')] for key, values in batches.items()}
            batches = {key: values for key, values in batches.items() if values}
        pages = max(1, (len(batches)+per_page-1)//per_page)
        page = min(page, pages)
        return {'batches': list(batches.items())[(page-1)*per_page:page*per_page],
                'page': page, 'pages': pages, 'total': len(batches), 'source': source}

    def image(self, batch_id, name, size='display'):
        if size not in ('display', 'thumb'):
            raise ValueError('Unknown image size')
        original = self.original(batch_id, name)
        # Browser-sized derived file; retain the untouched full original.
        stat = original.stat()
        cache = self.root / 'gallery-cache' / batch_id / (f'{name}-{stat.st_size}-{stat.st_mtime_ns}' + ('-thumb.jpg' if size == 'thumb' else '.jpg'))
        # Keep thumbnail work from delaying the selected review image.
        with self.thumbnail_lock if size == 'thumb' else self.display_lock:
            if not cache.exists():
                with Image.open(original) as im:
                    im.seek(0)
                    # JPEG scaled decoding avoids loading a full camera original
                    # just to make a small thumbnail. Preserve EXIF orientation.
                    im.draft('RGB', (480,480) if size == 'thumb' else (1920,1920))
                    image = ImageOps.exif_transpose(im).convert('RGB')
                    image.thumbnail((480,480) if size == 'thumb' else (1920,1920), Image.Resampling.LANCZOS)
                    data = io.BytesIO(); image.save(data,'JPEG',quality=82 if size == 'thumb' else 90)
                atomic_bytes(cache,data.getvalue())
        return cache
