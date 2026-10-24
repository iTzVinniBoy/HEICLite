"""Seleciona arquivos no Explorador usando a API nativa do Windows."""
import ctypes
from ctypes import wintypes
from collections import defaultdict
from pathlib import Path


def select_files(paths):
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    ole = ctypes.WinDLL('ole32')
    parse = shell.SHParseDisplayName
    parse.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    parse.restype = ctypes.c_long
    last = shell.ILFindLastID
    last.argtypes = [ctypes.c_void_p]
    last.restype = ctypes.c_void_p
    show = shell.SHOpenFolderAndSelectItems
    show.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD]
    show.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole.CoInitialize.argtypes = [ctypes.c_void_p]
    ole.CoInitialize.restype = ctypes.c_long
    initialized = ole.CoInitialize(None) >= 0
    groups = defaultdict(list)
    for path in paths:
        path = Path(path).resolve()
        if path.is_file():
            groups[path.parent].append(path)
    try:
        for folder, files in groups.items():
            allocations = []
            def pidl(path):
                pointer = ctypes.c_void_p()
                if parse(str(path), None, ctypes.byref(pointer), 0, None) < 0:
                    raise OSError(f'Não foi possível localizar {path.name} no Explorador.')
                allocations.append(pointer)
                return pointer
            try:
                parent = pidl(folder)
                children = (ctypes.c_void_p * len(files))(*(last(pidl(p)) for p in files))
                if show(parent, len(files), children, 0) < 0:
                    raise OSError('Não foi possível selecionar os arquivos no Explorador.')
            finally:
                for pointer in allocations:
                    ole.CoTaskMemFree(pointer)
    finally:
        if initialized:
            ole.CoUninitialize()
