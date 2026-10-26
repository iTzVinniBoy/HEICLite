"""Transfere a seleção para o processo administrativo; não executa conversões."""
import atexit
import hashlib
import json
import os
import tempfile
from pathlib import Path

_owned=[]


def create_handoff(paths,backup='',quality='75'):
    data=json.dumps(dict(paths=[str(p) for p in paths],backup=backup,quality=quality),ensure_ascii=False).encode('utf-8')
    with tempfile.NamedTemporaryFile(prefix='heiclite-fila-',suffix='.json',delete=False) as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
        path=Path(stream.name)
    _owned.append(path)
    return str(path),hashlib.sha256(data).hexdigest()


def read_handoff(path,checksum):
    with Path(path).open('rb') as stream: data=stream.read(4*1024*1024+1)
    if len(data)>4*1024*1024 or hashlib.sha256(data).hexdigest()!=checksum:
        raise ValueError('A fila recebida foi alterada. Abra novamente pela janela normal.')
    result=json.loads(data.decode('utf-8'))
    paths=result.get('paths')
    if not isinstance(paths,list) or not paths or len(paths)>10000 or any(not isinstance(p,str) or not Path(p).is_absolute() for p in paths):
        raise ValueError('Fila de pastas inválida.')
    if not isinstance(result.get('backup'),str) or not isinstance(result.get('quality'),str): raise ValueError('Opções inválidas.')
    return result


@atexit.register
def cleanup():
    for path in _owned:
        try: path.unlink(missing_ok=True)
        except OSError: pass
