"""Vistorias: pastas sequenciais, cópia verificada, diário durável e recuperação."""
import csv
import hashlib
import multiprocessing
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager, nullcontext
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path

from PIL import Image
from converter import convert_photo, EXTENSIONS
from safe_files import LockedFile, digest_file, digest_stream, is_link, publish_exclusive, reject_links
from admin import require_admin


def prepare_locations(root, backup):
    root = reject_links(root)
    backup = reject_links(backup)
    if not root.is_dir():
        raise ValueError('Selecione uma pasta de vistorias disponível.')
    if root == backup or root in backup.parents or backup in root.parents:
        raise ValueError('O backup deve ficar fora da pasta de vistorias, sem conter essa pasta.')
    identity = hashlib.sha256(str(root).casefold().encode()).hexdigest()[:12]
    namespace = backup / f'HEICLite-{root.name or "raiz"}-{identity}'
    namespace.mkdir(parents=True, exist_ok=True)
    reject_links(namespace)
    with connect(namespace) as db:
        db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)')
        existing = db.execute("SELECT value FROM metadata WHERE key='root'").fetchone()
        if existing and existing['value'] != str(root):
            raise ValueError('Este diário pertence a outra pasta de origem.')
        db.execute("INSERT OR IGNORE INTO metadata VALUES ('root', ?)", (str(root),))
        db.execute('CREATE TABLE IF NOT EXISTS jobs (source TEXT, hash TEXT, backup TEXT, jpeg TEXT, jpeg_hash TEXT, size_before INTEGER, size_after INTEGER, state TEXT, PRIMARY KEY(source, hash))')
        db.execute('CREATE TABLE IF NOT EXISTS history (run TEXT, time TEXT, source TEXT, status TEXT, jpeg TEXT, backup TEXT, detail TEXT)')
    return root, namespace


@contextmanager
def connect(namespace):
    db = sqlite3.connect(Path(namespace) / 'manifesto.sqlite3', timeout=30)
    db.execute('PRAGMA synchronous=FULL')
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def record(namespace, run, result):
    with connect(namespace) as db:
        db.execute('INSERT INTO history VALUES (?,?,?,?,?,?,?)', (
            run, time.strftime('%Y-%m-%d %H:%M:%S'), result.get('source', ''), result['status'],
            result.get('jpeg', ''), result.get('backup', ''), result.get('detail', '')))


def copy_backup(source, source_stream, source_hash, root, namespace):
    relative = source.relative_to(root)
    folder = namespace / 'originais' / relative.parent
    reject_links(folder)
    folder.mkdir(parents=True, exist_ok=True)
    backup = folder / f'{source.stem}.{source_hash[:20]}{source.suffix}'
    if backup.exists():
        if is_link(backup) or digest_file(backup) != source_hash:
            raise ValueError('Backup existente não confere. Original preservado; verifique a cópia.')
        return backup
    temporary = folder / f'.heiclite-{uuid.uuid4().hex}.part'
    try:
        source_stream.seek(0)
        with temporary.open('xb') as target:
            while chunk := source_stream.read(1024 * 1024):
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        if digest_file(temporary) != source_hash:
            raise ValueError('A cópia não confere com o original. Original preservado.')
        info = os.fstat(source_stream.fileno())
        os.utime(temporary, ns=(info.st_atime_ns, info.st_mtime_ns))
        publish_exclusive(temporary, backup)
        return backup
    finally:
        temporary.unlink(missing_ok=True)


def inspect_backup(stream):
    stream.seek(0)
    with Image.open(stream) as image:
        image.load()
        return image.size, getattr(image, 'n_frames', 1)


def process_inspection_file(source, root, namespace, quality=75, backup_enabled=True):
    """Remove só depois do backup, JPEG e diário verificados, com locks ativos."""
    source, root, namespace = map(Path, (source, root, namespace))
    result = {'source': str(source), 'status': 'error', 'detail': '', 'removed': False}
    try:
        require_admin()
        source = reject_links(source)
        if root not in source.parents or source.suffix.lower() not in EXTENSIONS:
            raise ValueError('Foto fora da raiz selecionada ou extensão incompatível.')
        with LockedFile(source, removable=True) as original:
            before = os.fstat(original.stream.fileno()).st_size
            source_hash = digest_stream(original.stream)
            backup = copy_backup(source, original.stream, source_hash, root, namespace) if backup_enabled else None
            result['backup'] = str(backup) if backup else ''
            with (LockedFile(backup) if backup else nullcontext(original)) as protected_backup:
                if backup_enabled and digest_stream(protected_backup.stream) != source_hash:
                    raise ValueError('Falha na releitura do backup. Original preservado.')
                expected_size, frames = inspect_backup(protected_backup.stream)
                # Um JPEG único não representa todas as fotos de um HEIF multiquadro.
                if frames != 1:
                    result.update(status='retained', detail=f'HEIF com {frames} imagens: original mantido para revisão.')
                    return result
                with connect(namespace) as db:
                    previous = db.execute('SELECT * FROM jobs WHERE source=? AND hash=?', (str(source), source_hash)).fetchone()
                jpeg = None
                valid_states=('verified', 'removed') if backup_enabled else ('verified_no_backup','removed_no_backup')
                if previous and previous['state'] in valid_states:
                    candidate = Path(previous['jpeg'])
                    if candidate.parent == source.parent and candidate.is_file() and not is_link(candidate) and digest_file(candidate) == previous['jpeg_hash']:
                        jpeg = candidate
                if jpeg is None:
                    if backup_enabled:
                        jpeg = convert_photo(backup, quality, source.parent, output_stem=source.stem)
                    else:
                        jpeg = convert_photo(source, quality, source.parent, output_stem=source.stem, source_stream=original.stream)
                result['jpeg'] = str(jpeg)
                with LockedFile(jpeg) as protected_jpeg:
                    with Image.open(protected_jpeg.stream) as check:
                        check.load()
                        if check.format != 'JPEG' or check.size != expected_size:
                            raise ValueError('JPEG não passou na validação de formato e dimensões.')
                    jpeg_hash = digest_stream(protected_jpeg.stream)
                    after = os.fstat(protected_jpeg.stream.fileno()).st_size
                    if digest_stream(original.stream) != source_hash or (backup_enabled and digest_stream(protected_backup.stream) != source_hash):
                        raise ValueError('Original ou backup alterado. Original preservado.')
                    # Commit FULL antes de autorizar a remoção; falha de disco mantém o original.
                    with connect(namespace) as db:
                        db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?,?,?)',
                                   (str(source), source_hash, str(backup) if backup else '', str(jpeg), jpeg_hash, before, after, valid_states[0]))
                    original.remove_on_close()
                    # Fechar aqui mantém backup/JPEG bloqueados até a remoção se concluir.
                    original.stream.close()
                    result.update(status='ok', removed=True, before=before, after=after,
                                  detail='JPEG validado • HEIC retirado • '+('backup conferido' if backup_enabled else 'SEM BACKUP • sem restauração do HEIC'))
                    with connect(namespace) as db:
                        db.execute("UPDATE jobs SET state=? WHERE source=? AND hash=?", (valid_states[1], str(source), source_hash))
        return result
    except Exception as error:
        result['status'] = 'error'
        result['detail'] = str(error)
        if result['removed']:
            result['detail'] = ('JPEG e backup salvos' if backup_enabled else 'JPEG salvo, HEIC removido SEM BACKUP')+'; falha ao finalizar o diário: ' + str(error)
        return result


def walk_folders(root, stop, notify):
    """DFS iterativo; só armazena caminhos, nunca carrega as fotos na varredura."""
    stack = [Path(root)]
    while stack and not stop.is_set():
        folder = stack.pop()
        photos, children = [], []
        try:
            if is_link(folder):
                notify({'source':str(folder),'status':'retained','detail':'Link ou junção ignorado.'})
                continue
            with os.scandir(folder) as entries:
                for entry in entries:
                    if stop.is_set():
                        return
                    path = Path(entry.path)
                    directory=entry.is_dir(follow_symlinks=False)
                    candidate=path.suffix.lower() in EXTENSIONS
                    if not directory and not candidate: continue
                    if entry.is_symlink() or bool(getattr(entry.stat(follow_symlinks=False),'st_file_attributes',0)&0x400):
                        notify({'source': str(path), 'status': 'retained', 'detail': 'Link ou junção ignorado.'})
                    elif directory:
                        children.append(path)
                    elif entry.is_file(follow_symlinks=False) and path.suffix.lower() in EXTENSIONS:
                        photos.append(path)
        except OSError as error:
            notify({'source': str(folder), 'status': 'error', 'detail': f'Falha na varredura: {error}'})
            continue
        stack.extend(sorted(children, reverse=True))
        yield folder, sorted(photos)


class RunLock:
    def __init__(self, namespace):
        self.path = Path(namespace) / 'execucao.lock'

    def __enter__(self):
        self.file = self.path.open('a+b')
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b'0')
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError('Outra execução já está usando este backup. Aguarde sua conclusão.')
        return self

    def __exit__(self, *args):
        self.file.close()


def export_report(namespace, run):
    report = Path(namespace) / f'relatorio-{run}.csv'
    with connect(namespace) as db, report.open('w', encoding='utf-8-sig', newline='') as target:
        writer = csv.writer(target, delimiter=';')
        writer.writerow(['execucao', 'data', 'original', 'situacao', 'jpeg', 'backup', 'detalhe'])
        for row in db.execute('SELECT * FROM history WHERE run=? ORDER BY rowid', (run,)):
            # Evita que caminhos sejam interpretados como fórmulas no Excel.
            writer.writerow(["'" + str(value) if str(value).startswith(('=', '+', '-', '@')) else value for value in row])
        target.flush()
        os.fsync(target.fileno())
    return report


def run_inspections(root, backup, events, stop, quality=75, max_workers=4, backup_enabled=True, plan=None):
    stats = dict(visited=0, folders=0, converted=0, removed=0, retained=0, errors=0, before=0, after=0)
    run = time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
    namespace = None

    def notify(result):
        if result['status'] == 'ok':
            stats['converted'] += 1
            stats['removed'] += bool(result.get('removed'))
            stats['before'] += result['before']
            stats['after'] += result['after']
        elif result['status'] == 'retained':
            stats['retained'] += 1
        else:
            stats['errors'] += 1
        record(namespace, run, result)
        events.put(('inspection_result', result, dict(stats)))

    try:
        require_admin()
        root, namespace = prepare_locations(root, backup)
        events.put(('inspection_backup', str(namespace)))
        if plan:
            for result in plan.issues(): notify(result)
        with RunLock(namespace), ProcessPoolExecutor(max_workers=max(1, min(max_workers, 4)), mp_context=multiprocessing.get_context('spawn')) as pool:
            for folder, photos in (plan.groups(stop) if plan else walk_folders(root, stop, notify)):
                stats['visited'] += 1
                if not photos:
                    if stats['visited'] % 25 == 0:
                        events.put(('inspection_scan', str(folder), dict(stats)))
                    continue
                stats['folders'] += 1
                events.put(('inspection_folder', str(folder), len(photos), dict(stats)))
                remaining = iter(photos)
                active = {}
                exhausted = False
                # Não avança para a próxima pasta enquanto houver qualquer foto ativa.
                while active or not exhausted:
                    while not stop.is_set() and not exhausted and len(active) < max(1, min(max_workers, 4)):
                        try:
                            path = next(remaining)
                        except StopIteration:
                            exhausted = True
                            break
                        args=(path,root,namespace,quality) if backup_enabled else (path,root,namespace,quality,False)
                        active[pool.submit(process_inspection_file, *args)] = path
                    if stop.is_set():
                        exhausted = True
                    if not active:
                        break
                    completed, _ = wait(active, timeout=0.15, return_when=FIRST_COMPLETED)
                    for future in completed:
                        path = active.pop(future)
                        try:
                            result = future.result()
                        except Exception as error:
                            result = dict(source=str(path), status='error', detail=str(error))
                        notify(result)
                events.put(('inspection_folder_done', str(folder)))
                if stop.is_set():
                    break
    except Exception as error:
        stats['errors'] += 1
        events.put(('inspection_fatal', str(error)))
    finally:
        if namespace:
            try:
                stats['report'] = str(export_report(namespace, run))
            except Exception as error:
                stats['errors'] += 1
                events.put(('inspection_fatal', f'Falha ao exportar CSV. O diário SQLite foi mantido: {error}'))
            stats['backup'] = str(namespace)
        stats['cancelled'] = stop.is_set()
        events.put(('inspection_done', stats))


def restore_originals(namespace):
    """Restaura por cópia conferida; nunca substitui um arquivo existente."""
    require_admin()
    namespace = reject_links(namespace)
    restored, skipped = 0, 0
    with RunLock(namespace), connect(namespace) as db:
        metadata = db.execute("SELECT value FROM metadata WHERE key='root'").fetchone()
        if not metadata:
            raise ValueError('Diário sem identificação da pasta de origem.')
        root = reject_links(metadata['value'])
        rows = db.execute("SELECT * FROM jobs WHERE backup IS NOT NULL AND backup <> ''")
        for row in rows:
            source, backup = Path(row['source']), Path(row['backup'])
            if root not in source.resolve().parents or source.suffix.lower() not in EXTENSIONS:
                raise ValueError('Registro de origem fora da pasta da vistoria.')
            reject_links(source.parent)
            reject_links(backup)
            if namespace not in backup.parents:
                raise ValueError('Caminho de backup fora da pasta do diário.')
            if source.exists():
                skipped += 1
                continue
            with LockedFile(backup) as protected:
                if digest_stream(protected.stream) != row['hash']:
                    raise ValueError(f'Backup alterado: {backup}. Restauração interrompida.')
                source.parent.mkdir(parents=True, exist_ok=True)
                temporary = source.parent / f'.heiclite-{uuid.uuid4().hex}.part'
                try:
                    with temporary.open('xb') as target:
                        while chunk := protected.stream.read(1024 * 1024):
                            target.write(chunk)
                        target.flush()
                        os.fsync(target.fileno())
                    if digest_file(temporary) != row['hash']:
                        raise ValueError('Falha na verificação da restauração.')
                    publish_exclusive(temporary, source)
                    restored += 1
                finally:
                    temporary.unlink(missing_ok=True)
    return restored, skipped
