"""Índice local de caminhos: uma varredura, consumo por pasta, sem armazenar fotos."""
import hashlib
import json
import os
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from inspection import walk_folders


class ScanCancelled(Exception): pass


def cache_directory():
    return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'HEICLite'/'indices'


def cache_path(root):
    key=hashlib.sha256(str(root).casefold().encode()).hexdigest()
    return cache_directory()/(key+'.sqlite3')


class ScanPlan:
    def __init__(self,path,root):
        self.path=Path(path)
        self.root=Path(root)
        with closing(sqlite3.connect(self.path)) as db:
            self.meta=json.loads(db.execute('SELECT value FROM metadata').fetchone()[0])
        self.origin=Path(self.meta['root'])
        self.relative=self.root.relative_to(self.origin).as_posix()

    def condition(self,column='folder'):
        if self.relative=='.': return '1',()
        prefix=self.relative+'/'
        return f'({column}=? OR substr({column},1,?)=?)',(self.relative,len(prefix),prefix)

    def count(self):
        where,args=self.condition()
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT count(*) FROM files WHERE '+where,args).fetchone()[0]

    def covers_root(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT 1 FROM folders WHERE path=?',(self.relative,)).fetchone() is not None

    def issues(self):
        with closing(sqlite3.connect(self.path)) as db:
            for raw, in db.execute('SELECT value FROM issues'):
                result=json.loads(raw)
                source=Path(result['source'])
                if source==self.root or self.root in source.parents: yield result

    def groups(self,stop):
        where,args=self.condition('path')
        last=''
        while not stop.is_set():
            with closing(sqlite3.connect(self.path)) as db:
                rows=db.execute('SELECT path FROM folders WHERE '+where+' AND path>? AND EXISTS (SELECT 1 FROM files WHERE folder=folders.path) ORDER BY path LIMIT 100',(*args,last)).fetchall()
            if not rows: return
            for relative, in rows:
                if stop.is_set(): return
                folder=self.origin/Path(relative)
                if '..' in Path(relative).parts or Path(relative).is_absolute() or (folder!=self.root and self.root not in folder.parents):
                    raise ValueError('Índice contém pasta fora da origem selecionada. Atualize a análise.')
                with closing(sqlite3.connect(self.path)) as db:
                    names=[value for value, in db.execute('SELECT path FROM files WHERE folder=? ORDER BY path',(relative,))]
                photos=[]
                for name in names:
                    path=self.origin/Path(name)
                    if '..' in Path(name).parts or Path(name).is_absolute() or path.parent!=folder:
                        raise ValueError('Índice contém foto fora da pasta. Atualize a análise.')
                    photos.append(path)
                if photos: yield folder,photos
                last=relative

    def forget_removed(self,paths):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executemany('DELETE FROM files WHERE path=?',[(Path(p).relative_to(self.origin).as_posix(),) for p in paths])


def find_plan(root):
    root=Path(root)
    for parent in (root,*root.parents):
        path=cache_path(parent)
        if not path.is_file(): continue
        try:
            plan=ScanPlan(path,root)
            if plan.meta.get('version')==1 and plan.meta.get('complete') and not plan.meta.get('errors') and plan.covers_root():
                return plan
        except (OSError,sqlite3.Error,ValueError,KeyError,TypeError): continue
    return None


def analyze(root,events,stop,force=False):
    if stop.is_set(): raise ScanCancelled()
    if not force:
        plan=find_plan(root)
        if plan:
            events.put(('analysis_cached',str(root),plan.meta['created'],plan.count()))
            return plan
    target=cache_path(root)
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.'+uuid.uuid4().hex+'.part')
    visited=photos_count=empty=errors=0
    last_update=0
    try:
        with closing(sqlite3.connect(temporary)) as db:
            db.executescript('CREATE TABLE metadata(value TEXT); CREATE TABLE folders(path TEXT PRIMARY KEY); CREATE TABLE files(path TEXT PRIMARY KEY,folder TEXT); CREATE INDEX files_folder ON files(folder); CREATE TABLE issues(value TEXT);')
            def issue(result):
                nonlocal errors
                if result['status']=='error': errors+=1
                db.execute('INSERT INTO issues VALUES (?)',(json.dumps(result,ensure_ascii=False),))
            events.put(('analysis_progress',str(root),0,0,0,0))
            for folder,photos in walk_folders(root,stop,issue):
                if stop.is_set(): raise ScanCancelled()
                relative=folder.relative_to(root).as_posix()
                db.execute('INSERT INTO folders VALUES (?)',(relative,))
                db.executemany('INSERT INTO files VALUES (?,?)',[(p.relative_to(root).as_posix(),relative) for p in photos])
                visited+=1; photos_count+=len(photos); empty+=not photos
                if visited%100==0: db.commit()
                now=time.monotonic()
                if now-last_update>=.2:
                    events.put(('analysis_progress',str(folder),visited,photos_count,empty,errors))
                    last_update=now
            if stop.is_set(): raise ScanCancelled()
            meta=dict(version=1,root=str(root),created=time.strftime('%Y-%m-%d %H:%M:%S'),complete=True,errors=errors,visited=visited,empty=empty)
            db.execute('INSERT INTO metadata VALUES (?)',(json.dumps(meta,ensure_ascii=False),))
            db.commit()
        os.replace(temporary,target)
        events.put(('analysis_progress',str(root),visited,photos_count,empty,errors))
        return ScanPlan(target,root)
    finally: temporary.unlink(missing_ok=True)
