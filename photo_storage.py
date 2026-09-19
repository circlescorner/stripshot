"""Optional extra copies. Recovery originals are always retained byte-for-byte."""
import copy
import hashlib
import io
import json
import queue
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image
from storage import atomic_bytes, save_json
from storage_location import fingerprint

DEFAULT={'enabled':False,'folder':'','grouping':'date','originals':True,'sheet':True,'strips':False,'quality':95,'name':'Stripshot'}


class PhotoStorage:
    def __init__(self,root):
        self.root=Path(root);self.path=self.root/'operator-storage.json'
        self.settings=json.loads(self.path.read_text()) if self.path.exists() else dict(DEFAULT)
        self.settings={**DEFAULT,**self.settings}
        self.validate(self.settings,check_folder=False)
        self.jobs=queue.Queue();self.lock=threading.Lock();self.stopping=threading.Event()
        self.notice='Extra copies disabled' if not self.settings['enabled'] else 'Ready'
        self.latest=None;self.records={}
        self.thread=threading.Thread(target=self.run,name='photo-export',daemon=True)

    def validate(self,value,check_folder=True):
        if not isinstance(value,dict) or not set(DEFAULT)<=set(value) or set(value)-set(DEFAULT)-{'folder_identity'}:
            raise ValueError('Invalid photo storage settings')
        if any(type(value[k]) is not bool for k in ('enabled','originals','sheet','strips')):
            raise ValueError('Choose which extra copies to save')
        if value['grouping'] not in ('date','batch') or type(value['quality']) is not int or not 60<=value['quality']<=100:
            raise ValueError('Choose date/batch folders and JPEG quality 60–100')
        if not isinstance(value['folder'],str):raise ValueError('Choose an absolute destination folder')
        if not isinstance(value['name'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,48}',value['name']):
            raise ValueError('Session name: 1–48 letters, numbers, underscores or hyphens')
        if value['enabled']:
            if not any(value[k] for k in ('originals','sheet','strips')):raise ValueError('Select at least one extra-copy format')
            folder=Path(value['folder']).expanduser()
            if not folder.is_absolute():raise ValueError('Use an absolute extra-copy folder path')
            if check_folder:
                folder=folder.resolve()
                if not folder.is_dir():raise ValueError('The extra-copy destination must be an existing folder')
                if folder==self.root.resolve() or folder.is_relative_to(self.root.resolve()):
                    raise ValueError('Extra copies must be outside the recovery storage folder')
                value['folder']=str(folder);value['folder_identity']=fingerprint(folder)

    def save(self,candidate):
        candidate=copy.deepcopy(candidate);self.validate(candidate)
        with self.lock:
            save_json(self.path,candidate);self.settings=candidate

    def status(self):
        with self.lock:return {'settings':copy.deepcopy(self.settings),'message':self.notice,'latest':copy.deepcopy(self.latest),
                              'failed_jobs':[copy.deepcopy(r) for r in self.records.values() if r['status']=='failed']}

    def enqueue(self,batch,manual=False):
        settings=copy.deepcopy(self.settings if manual else batch.get('storage',DEFAULT))
        if not settings['enabled']:return None
        ident='export-'+uuid.uuid4().hex if manual else batch['id']
        path=self.root/'storage-jobs'/f'{ident}.json'
        with self.lock:
            if path.exists():return ident
            record={'id':ident,'batch_id':batch['id'],'settings':settings,'created_at':time.time(),'status':'pending'}
            save_json(path,record);self.latest=record;self.records[ident]=record;self.jobs.put(record)
        return ident

    def start(self,last):
        for path in sorted((self.root/'storage-jobs').glob('*.json')):
            try:
                record=json.loads(path.read_text());self.latest=record;self.records[record['id']]=record
                if record['status'] in ('pending','copying'):self.jobs.put(record)
            except (ValueError,OSError,KeyError):self.notice='An export record is unreadable; inspect storage-jobs'
        if last:
            try:self.enqueue(last)
            except Exception as exc:self.notice='Cannot queue extra copies: '+str(exc)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread.ident is not None:self.thread.join(2)

    def review(self,candidate):
        if not isinstance(candidate,dict) or set(candidate)!={'note'} or not isinstance(candidate['note'],str) or not 1<=len(candidate['note'])<=1000:
            raise ValueError('Enter a retention review note (1–1000 characters)')
        path=self.root/'retention-reviews'/(uuid.uuid4().hex+'.json')
        save_json(path,{'reviewed_at':time.time(),'note':candidate['note'],'action':'retain_all_no_deletion'})
        return {'message':'Review recorded. All files retained; nothing deleted.'}

    def retry(self,ident):
        if not isinstance(ident,str) or '/' in ident or '..' in ident:raise ValueError('Invalid export job')
        path=self.root/'storage-jobs'/f'{ident}.json'
        with self.lock:
            record=json.loads(path.read_text())
            if record['status']!='failed':raise ValueError('Only failed copies can be retried')
            record['status']='pending';record.pop('error',None);save_json(path,record);self.records[ident]=record;self.jobs.put(record)

    def run(self):
        while not self.stopping.is_set():
            try:record=self.jobs.get(timeout=.2)
            except queue.Empty:continue
            try:
                record['status']='copying';save_json(self.root/'storage-jobs'/f"{record['id']}.json",record)
                self.copy_job(record);record['status']='complete'
            except Exception as exc:record.update(status='failed',error=str(exc))
            try:save_json(self.root/'storage-jobs'/f"{record['id']}.json",record)
            except Exception as exc:record.update(status='failed',error='Could not save copy status: '+str(exc))
            with self.lock:
                self.latest=copy.deepcopy(record)
                self.notice='Extra copies saved' if record['status']=='complete' else 'Extra copies failed: '+record.get('error','Unknown error')

    def copy_job(self,record):
        settings=record['settings'];folder=Path(settings['folder'])
        if not folder.is_dir() or fingerprint(folder)!=settings.get('folder_identity'):
            raise RuntimeError('Extra-copy folder is unavailable or changed; reconnect it or save a new destination')
        source=self.root/'batches'/record['batch_id'];batch=json.loads((source/'manifest.json').read_text())
        if batch.get('stage')!='complete':raise ValueError('Only completed batches can be copied')
        date=datetime.fromtimestamp(batch['completed_at'],timezone.utc).strftime('%Y-%m-%d')
        target=folder/(date if settings['grouping']=='date' else 'batches')/(settings.get('name','Stripshot')+'-'+record['id'])
        target.mkdir(parents=True,exist_ok=True)
        hashes={}
        def write(name,data):
            if self.stopping.is_set():raise RuntimeError('Copy interrupted by shutdown; originals retained')
            expected=hashlib.sha256(data).hexdigest();path=target/name
            if path.exists():
                if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise RuntimeError('Refusing to overwrite different file: '+str(path))
            else:atomic_bytes(path,data)
            if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise RuntimeError('Extra-copy verification failed')
            hashes[name]=expected
        if settings['originals']:
            for c in ('A','B'):
                for n in range(1,9):
                    name=f'{c}{n:02d}.jpg';data=(source/name).read_bytes()
                    if batch.get('software') and hashlib.sha256(data).hexdigest()!=batch['shots'][c][n-1].get('sha256'):
                        raise RuntimeError('Original hash mismatch; copy stopped')
                    write(name,data)
        if settings['sheet']:write('sheet.png',(source/'sheet.png').read_bytes())
        if settings['strips']:
            with Image.open(source/'sheet.png') as sheet:
                for n in range(4):
                    data=io.BytesIO();sheet.crop((600*n,0,600*(n+1),1800)).convert('RGB').save(data,'JPEG',quality=settings['quality'])
                    write(f'strip{n+1}.jpg',data.getvalue())
        write('manifest.json',(json.dumps({'source_batch':record['batch_id'],'files':hashes,'settings':settings},indent=2)+'\n').encode())
        record['destination']=str(target)
