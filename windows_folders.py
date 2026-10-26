"""Seletor moderno do Explorer (IFileOpenDialog), incluindo locais de rede."""
import ctypes
from ctypes import wintypes
import json
import base64
import uuid

NETWORK_PLACES = []


def mapped_places():
    kernel = ctypes.WinDLL('kernel32')
    kernel.GetLogicalDrives.restype = wintypes.DWORD
    kernel.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    kernel.GetDriveTypeW.restype = wintypes.UINT
    mpr = ctypes.WinDLL('mpr.dll')
    get = mpr.WNetGetConnectionW
    get.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    get.restype = wintypes.DWORD
    drives = kernel.GetLogicalDrives()
    places = []
    for i in range(26):
        drive = chr(65+i)+':'
        if drives & (1 << i) and kernel.GetDriveTypeW(drive+'\\') == 4:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if get(drive,buffer,ctypes.byref(size)) == 0:
                places.append(buffer.value)
    return places


def encode_places(places):
    return base64.urlsafe_b64encode(json.dumps(places,ensure_ascii=False).encode('utf-8')).decode('ascii')


def decode_places(value):
    if len(value)>65536: raise ValueError('Lista de rede inválida.')
    places=json.loads(base64.urlsafe_b64decode(value).decode('utf-8'))
    if not isinstance(places,list) or len(places)>26: raise ValueError('Lista de rede inválida.')
    if any(not isinstance(p,str) or not p.startswith('\\\\') or p.startswith(('\\\\?\\','\\\\.\\')) for p in places):
        raise ValueError('A lista de rede deve conter apenas compartilhamentos UNC.')
    return list(dict.fromkeys(places))


def guid(value):
    return (ctypes.c_byte*16).from_buffer_copy(uuid.UUID(value).bytes_le)


def invoke(pointer,index,types=(),args=()):
    table=ctypes.cast(pointer,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    method=ctypes.WINFUNCTYPE(ctypes.c_long,ctypes.c_void_p,*types)(table[index])
    return method(pointer,*args)


def check(result):
    if result < 0: raise OSError(f'Falha no seletor do Windows (0x{result & 0xffffffff:08X}).')


def choose_native_folder(parent,title='Selecionar pasta',initial='',multiple=False):
    # WinDLL mantém HRESULTs como valores, inclusive o cancelamento do usuário.
    ole=ctypes.WinDLL('ole32')
    ole.CoInitializeEx.argtypes=[ctypes.c_void_p,wintypes.DWORD]
    ole.CoInitializeEx.restype=ctypes.c_long
    initialized=ole.CoInitializeEx(None,2)
    if initialized < 0: check(initialized)
    dialog=ctypes.c_void_p()
    shell=ctypes.WinDLL('shell32')
    shell.SHCreateItemFromParsingName.argtypes=[wintypes.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p)]
    shell.SHCreateItemFromParsingName.restype=ctypes.c_long
    ole.CoCreateInstance.argtypes=[ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p)]
    ole.CoCreateInstance.restype=ctypes.c_long
    ole.CoTaskMemFree.argtypes=[ctypes.c_void_p]
    item_id=guid('43826d1e-e718-42ee-bc55-a1e261c37bfe')
    def item(path):
        result=ctypes.c_void_p()
        check(shell.SHCreateItemFromParsingName(path,None,ctypes.byref(item_id),ctypes.byref(result)))
        return result
    try:
        clsid=guid('dc1c5a9c-e88a-4dde-a5a1-60f82a20aef7')
        iid=guid('d57c7288-d4ad-4768-be02-9d969532d960')
        check(ole.CoCreateInstance(ctypes.byref(clsid),None,1,ctypes.byref(iid),ctypes.byref(dialog)))
        options=wintypes.DWORD()
        check(invoke(dialog,10,(ctypes.POINTER(wintypes.DWORD),),(ctypes.byref(options),)))
        check(invoke(dialog,9,(wintypes.DWORD,),(options.value | 0x20 | 0x40 | 0x800 | (0x200 if multiple else 0),)))
        check(invoke(dialog,17,(wintypes.LPCWSTR,),(title,)))
        check(invoke(dialog,18,(wintypes.LPCWSTR,),('Selecionar pastas' if multiple else 'Selecionar pasta',)))
        for path in NETWORK_PLACES:
            try: place=item(path)
            except OSError: continue
            try: invoke(dialog,21,(ctypes.c_void_p,ctypes.c_int),(place,0))
            finally: invoke(place,2)
        if initial:
            try: folder=item(initial)
            except OSError: folder=None
            if folder:
                try: invoke(dialog,12,(ctypes.c_void_p,),(folder,))
                finally: invoke(folder,2)
        parent.update_idletasks()
        result=invoke(dialog,3,(wintypes.HWND,),(parent.winfo_id(),))
        if result & 0xffffffff == 0x800704c7: return [] if multiple else ''
        check(result)
        def selected_path(selected):
            path=ctypes.c_void_p()
            check(invoke(selected,5,(ctypes.c_int,ctypes.POINTER(ctypes.c_void_p)),(0x80058000,ctypes.byref(path))))
            try: return ctypes.wstring_at(path)
            finally: ole.CoTaskMemFree(path)
        if multiple:
            items=ctypes.c_void_p()
            check(invoke(dialog,27,(ctypes.POINTER(ctypes.c_void_p),),(ctypes.byref(items),)))
            try:
                count=wintypes.DWORD()
                check(invoke(items,7,(ctypes.POINTER(wintypes.DWORD),),(ctypes.byref(count),)))
                paths=[]
                for i in range(count.value):
                    selected=ctypes.c_void_p()
                    check(invoke(items,8,(wintypes.DWORD,ctypes.POINTER(ctypes.c_void_p)),(i,ctypes.byref(selected))))
                    try: paths.append(selected_path(selected))
                    finally: invoke(selected,2)
                return paths
            finally: invoke(items,2)
        selected=ctypes.c_void_p()
        check(invoke(dialog,20,(ctypes.POINTER(ctypes.c_void_p),),(ctypes.byref(selected),)))
        try:
            return selected_path(selected)
        finally: invoke(selected,2)
    finally:
        if dialog: invoke(dialog,2)
        ole.CoUninitialize()
