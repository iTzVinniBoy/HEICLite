"""Primitivas de arquivo: publicação exclusiva e bloqueio durante a remoção."""
import ctypes
import hashlib
import os
import stat
from pathlib import Path


def is_link(path):
    info = Path(path).lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def reject_links(path):
    path = Path(path).absolute()
    for part in [path, *path.parents]:
        if part.exists() and is_link(part):
            raise ValueError(f'Link, junção ou ponto de redirecionamento não permitido: {part}')
    return path.resolve()


def digest_stream(stream):
    stream.seek(0)
    checksum = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        checksum.update(chunk)
    stream.seek(0)
    return checksum.hexdigest()


def digest_file(path):
    with open(path, 'rb') as stream:
        return digest_stream(stream)


def publish_exclusive(temporary, target):
    """Publica um arquivo completo sem substituir um nome já existente."""
    if os.name == 'nt':
        os.rename(temporary, target)  # Windows: falha se target já existir.
    else:
        os.link(temporary, target)
        os.unlink(temporary)


class LockedFile:
    """No Windows, impede escrita/renomeação e apaga o MESMO objeto aberto.

    Não existe fallback para unlink de originais fora do Windows: falha fechada.
    """
    def __init__(self, path, removable=False):
        self.path = reject_links(path)
        self.removable = removable
        self.stream = None

    def __enter__(self):
        if os.name != 'nt':
            if self.removable:
                raise OSError('Remoção protegida disponível somente no Windows.')
            self.stream = self.path.open('rb')
            return self
        import msvcrt
        from ctypes import wintypes
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        create = self.kernel.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                           ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        name = str(self.path)
        if not name.startswith('\\\\?\\'):
            name = '\\\\?\\UNC\\' + name[2:] if name.startswith('\\\\') else '\\\\?\\' + name
        access = 0x80000000 | (0x10000 if self.removable else 0)
        handle = create(name, access, 1, None, 3, 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        self.handle = handle
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except Exception:
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.kernel.CloseHandle(handle)
            raise
        self.stream = os.fdopen(fd, 'rb')
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400 or info.st_nlink != 1:
            self.stream.close()
            raise ValueError('Arquivo especial, redirecionado ou com múltiplos links; original preservado.')
        return self

    def remove_on_close(self):
        if os.name != 'nt' or not self.removable:
            raise OSError('Este arquivo não foi aberto para remoção protegida.')
        from ctypes import wintypes
        operation = self.kernel.SetFileInformationByHandle
        operation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        operation.restype = wintypes.BOOL
        delete = ctypes.c_ubyte(1)
        if not operation(self.handle, 4, ctypes.byref(delete), ctypes.sizeof(delete)):
            raise ctypes.WinError(ctypes.get_last_error())

    def __exit__(self, *args):
        if self.stream:
            self.stream.close()
