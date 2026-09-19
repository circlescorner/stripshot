"""Stopped, locked, verified storage migration. Never move live batch state."""
import ctypes
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from storage import ProcessLock, save_json


def fingerprint(path):
    info=Path(path).stat()
    return {'device':info.st_dev,'inode':info.st_ino}


def destination_for(source, value):
    if not isinstance(value,str) or not value.strip() or not Path(value).expanduser().is_absolute():
        raise ValueError('Choose an absolute storage folder path')
    source=Path(source).resolve();destination=Path(value).expanduser().resolve()
    if destination==source or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Choose a separate folder outside the current data tree')
    if not destination.parent.is_dir():
        raise ValueError('The destination parent folder must already exist')
    if destination.exists():
        raise ValueError('The new main storage folder must not exist yet (choose a new folder)')
    return destination


def schedule_location(root, value):
    destination=destination_for(root,value)
    record={'destination':str(destination),'parent_identity':fingerprint(destination.parent),
            'destination_identity':fingerprint(destination) if destination.exists() else None}
    save_json(Path(root)/'storage-plans'/(uuid.uuid4().hex+'.json'),record)
    save_json(Path(root)/'storage-migration.json',record)
    return record


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


def inventory(root):
    records={}
    for path in sorted(Path(root).rglob('*')):
        if path.is_symlink():raise RuntimeError('Migration refuses symlinks; inspect '+str(path))
        relative=path.relative_to(root)
        if len(relative.parts)==1 and relative.name in ('stripshot.lock','storage-migration.json','storage-redirect.json'):continue
        if path.is_file():records[str(relative)]=(path.stat().st_size,digest(path))
        elif not path.is_dir():raise RuntimeError('Migration refuses non-regular files: '+str(path))
    return records


class StorageLease:
    def __init__(self,config):
        self.locks=[]
        try:
            root=Path(config['data_dir']).resolve()
            # Direct launches of the new location also retain all ancestral
            # locks, blocking old versions which only know the original lock.
            ancestry=set()
            while (root/'storage-origin.json').exists():
                if root in ancestry: raise RuntimeError('Storage origin loop')
                ancestry.add(root)
                child=root
                root=Path(json.loads((child/'storage-origin.json').read_text())['source']).resolve()
                if not root.exists():
                    # /tmp may disappear on reboot. Recreate only an empty alias,
                    # under its lock, never a replacement set of recovery data.
                    alias_lock=ProcessLock(root,allow_redirect=True)
                    try:
                        if any(p.name!='stripshot.lock' for p in root.iterdir()):
                            raise RuntimeError('Original alias changed while restoring it')
                        save_json(root/'storage-redirect.json',{'destination':str(child)})
                    finally: alias_lock.close()
                redirect=root/'storage-redirect.json'
                if not redirect.exists() or Path(json.loads(redirect.read_text())['destination']).resolve()!=child:
                    raise RuntimeError('Original storage alias is inconsistent; preserve both trees')
            visited=set()
            for _ in range(8):
                if root in visited:raise RuntimeError('Storage redirect loop; preserve the data and inspect')
                visited.add(root)
                self.locks.append(ProcessLock(root,allow_redirect=True))
                if (root/'storage-incomplete.json').exists():
                    raise RuntimeError('Interrupted storage migration; preserve both trees for recovery')
                redirect=root/'storage-redirect.json'
                if not redirect.exists():break
                root=Path(json.loads(redirect.read_text())['destination']).resolve()
                if not root.is_dir():raise RuntimeError('Redirected storage is unavailable; do not start from the old copy')
            else:raise RuntimeError('Too many storage redirects')
            pending=root/'storage-migration.json'
            record=json.loads(pending.read_text()) if pending.exists() else {'cancelled':True}
            if not record.get('cancelled'):
                destination=destination_for(root,record['destination'])
                if fingerprint(destination.parent)!=record['parent_identity']:
                    raise RuntimeError('Destination filesystem changed; reselect the storage folder')
                if record['destination_identity'] is not None and (not destination.exists() or fingerprint(destination)!=record['destination_identity']):
                    raise RuntimeError('Destination folder changed; reselect it')
                source_files=inventory(root)
                stage=destination.parent/('.stripshot-migration-'+uuid.uuid4().hex)
                print('Copying and verifying Stripshot storage: '+str(root)+' -> '+str(destination),flush=True)
                shutil.copytree(root,stage,ignore=lambda directory,names:
                                [n for n in names if Path(directory)==root and n in ('stripshot.lock','storage-migration.json','storage-redirect.json')])
                if inventory(stage)!=source_files or inventory(root)!=source_files:
                    raise RuntimeError('Storage copy changed or failed verification; source and staging preserved')
                for path in stage.rglob('*'):
                    if path.is_file():
                        with path.open('rb') as stream:os.fsync(stream.fileno())
                for directory in [p for p in stage.rglob('*') if p.is_dir()]+[stage]:
                    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
                    try:os.fsync(fd)
                    finally:os.close(fd)
                save_json(stage/'storage-origin.json',{'source':str(root)})
                save_json(stage/'storage-incomplete.json',{'source':str(root)})
                self.locks.append(ProcessLock(stage,allow_redirect=True))
                # The locked inode travels with the atomic rename. An exposed
                # destination is never unlocked, even before redirect commit.
                # Linux no-replace rename prevents a newly-created destination
                # (and its lock inode) from being replaced during the copy.
                libc=ctypes.CDLL(None,use_errno=True)
                if libc.renameat2(-100,os.fsencode(stage),-100,os.fsencode(destination),1):
                    code=ctypes.get_errno()
                    raise OSError(code,os.strerror(code),str(destination))
                fd=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(fd)
                finally:os.close(fd)
                # Redirect first: even a config-write failure can never reopen
                # the old independent copy as a fresh camera owner.
                save_json(root/'storage-redirect.json',{'destination':str(destination)})
                (destination/'storage-incomplete.json').unlink()
                fd=os.open(destination,os.O_RDONLY|os.O_DIRECTORY)
                try: os.fsync(fd)
                finally: os.close(fd)
                root=destination
            config['data_dir']=str(root)
            config_path=config.get('_config_path')
            if config_path:
                disk=json.loads(Path(config_path).read_text())
                if Path(disk.get('data_dir','data')).is_absolute() and disk['data_dir']==str(root):return
                original=(Path(config_path).parent/disk.get('data_dir','data')).resolve()
                if original!=root:
                    backup=Path(str(config_path)+'.before-storage-'+uuid.uuid4().hex+'.json')
                    shutil.copy2(config_path,backup)
                    disk['data_dir']=str(root);save_json(config_path,disk)
        except Exception:
            self.close();raise

    def close(self):
        for lock in reversed(self.locks):lock.close()
        self.locks=[]
