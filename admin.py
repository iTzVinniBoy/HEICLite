"""Elevação pelo UAC do Windows; o aplicativo nunca recebe senhas."""
import ctypes
import os
import subprocess
import sys
from pathlib import Path


def is_admin():
    if os.name != 'nt': return False
    try: return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError: return False


def require_admin():
    if not is_admin():
        raise PermissionError('Vistorias e restauração exigem uma janela elevada pelo administrador do Windows.')


def launch_admin(action='--vistorias-admin',folders=None,backup='',quality='75'):
    if action not in ('--vistorias-admin', '--restaurar-admin'):
        raise ValueError('Ação administrativa inválida.')
    if os.name != 'nt': raise OSError('Elevação disponível somente no Windows.')
    if getattr(sys, 'frozen', False):
        executable = Path(sys.executable)
        args = [action]
    else:
        executable = Path(sys.executable).with_name('pythonw.exe')
        args = [str(Path(__file__).resolve().with_name('app.py')), action]
    from windows_folders import mapped_places, encode_places
    places = mapped_places()
    if places:
        args.extend(['--rede-origem',encode_places(places)])
    if folders:
        from queue_handoff import create_handoff
        path,checksum=create_handoff(folders,backup,quality)
        args.extend(['--fila-origem',path,'--fila-hash',checksum])
    execute = ctypes.windll.shell32.ShellExecuteW
    execute.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                        ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int]
    execute.restype = ctypes.c_ssize_t
    result = execute(None, 'runas', str(executable), subprocess.list2cmdline(args), str(executable.parent), 1)
    if result <= 32:
        raise PermissionError('A autorização foi cancelada ou o Windows não permitiu abrir a janela administrativa.')
