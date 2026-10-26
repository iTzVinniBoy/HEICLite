import queue
import threading
import os
import sys
import multiprocessing
from pathlib import Path
import tempfile

# O executável sem console não tem stdout/stderr. Os processos de conversão
# precisam de streams válidos, inclusive para relatar uma falha de inicialização.
if getattr(sys, 'frozen', False):
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        try:
            sys.stderr = open(Path(tempfile.gettempdir()) / 'conversor-heic-erros.log', 'a', encoding='utf-8', buffering=1)
        except OSError:
            sys.stderr = open(os.devnull, 'w')

# Algumas instalações Python 3.13 não localizam Tcl/Tk dentro de um venv.
# No executável, o runtime é configurado pelo PyInstaller.
if not getattr(sys, 'frozen', False):
    for variable, folder in [('TCL_LIBRARY', 'tcl8.6'), ('TK_LIBRARY', 'tk8.6')]:
        location = Path(sys.base_prefix) / 'tcl' / folder
        if location.is_dir():
            os.environ.setdefault(variable, str(location))

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from converter import EXTENSIONS
from batch import run_batch, format_size, format_reduction, format_summary
from explorer import select_files


from ui import App

if __name__ == '__main__':
    multiprocessing.freeze_support()
    if len(sys.argv) in (3, 5) and sys.argv[1] == '--verificar-lote':
        # Verificação automatizada do EXE e dos seus próprios subprocessos.
        import json
        folder = Path(sys.argv[2])
        photos = sorted(p for p in folder.iterdir() if p.suffix.lower() in EXTENSIONS)
        events = queue.Queue()
        accelerated = threading.Event()
        accelerated.set()
        quality = int(sys.argv[3]) if len(sys.argv) == 5 else 75
        output_folder = Path(sys.argv[4]) if len(sys.argv) == 5 else None
        run_batch([(str(i), path) for i, path in enumerate(photos)], quality, events, accelerated, 2, output_folder)
        (folder / 'verificacao.json').write_text(json.dumps(list(events.queue), default=str, ensure_ascii=False), encoding='utf-8')
    elif len(sys.argv) == 3 and sys.argv[1] == '--verificar-interface':
        import json
        window = App()
        def verify_drop():
            # Regressão do EXE: drop assíncrono entregue durante mainloop.
            # Só adiciona a pasta temporária do relatório, sem converter arquivos.
            import ctypes
            import struct
            from ctypes import wintypes
            folder = str(Path(sys.argv[2]).resolve().parent)
            data = struct.pack('<IiiII',20,0,0,0,1)+(folder+'\0\0').encode('utf-16-le')
            kernel = ctypes.WinDLL('kernel32')
            kernel.GlobalAlloc.argtypes=[wintypes.UINT,ctypes.c_size_t]; kernel.GlobalAlloc.restype=wintypes.HGLOBAL
            kernel.GlobalLock.argtypes=[wintypes.HGLOBAL]; kernel.GlobalLock.restype=ctypes.c_void_p
            kernel.GlobalUnlock.argtypes=[wintypes.HGLOBAL]
            kernel.GlobalFree.argtypes=[wintypes.HGLOBAL]
            handle=kernel.GlobalAlloc(2,len(data))
            pointer=kernel.GlobalLock(handle)
            if not pointer:
                if handle: kernel.GlobalFree(handle)
                return
            ctypes.memmove(pointer,data,len(data)); kernel.GlobalUnlock(handle)
            user=ctypes.WinDLL('user32')
            user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
            if not user.PostMessageW(window.drop_label.winfo_id(),0x233,handle,0): kernel.GlobalFree(handle)
        def verify_interface():
            window.update_idletasks()
            Path(sys.argv[2]).write_text(json.dumps({'quality': window.quality.get(), 'mode': window.mode,
                'width': window.winfo_width(), 'button_visible': bool(window.convert_button.winfo_viewable()),
                'drop_received': Path(sys.argv[2]).resolve().parent in window.inspection_roots}), encoding='utf-8')
            window.destroy()
        window.after(250, verify_drop)
        window.after(1000, verify_interface)
        window.mainloop()
    elif len(sys.argv) == 4 and sys.argv[1] == '--verificar-vistorias':
        import json
        from inspection import run_inspections
        events = queue.Queue()
        run_inspections(Path(sys.argv[2]), Path(sys.argv[3]), events, threading.Event())
        (Path(sys.argv[3]) / 'verificacao.json').write_text(json.dumps(list(events.queue), default=str, ensure_ascii=False), encoding='utf-8')
    else:
        if '--rede-origem' in sys.argv:
            import windows_folders
            try:
                windows_folders.NETWORK_PLACES = windows_folders.decode_places(sys.argv[sys.argv.index('--rede-origem')+1])
            except (ValueError, IndexError):
                pass
        window = App()
        if any(flag in sys.argv for flag in ('--vistorias-admin','--restaurar-admin')):
            from admin import is_admin
            if not is_admin():
                window.withdraw()
                messagebox.showerror('Administrador necessário', 'O Windows não concedeu permissão de administrador. Nenhuma vistoria foi iniciada.')
                window.destroy()
                sys.exit(1)
            window.switch_mode('Vistorias')
            if '--fila-origem' in sys.argv:
                from queue_handoff import read_handoff
                from inspection_queue import selection_roots
                try:
                    selected=read_handoff(sys.argv[sys.argv.index('--fila-origem')+1],sys.argv[sys.argv.index('--fila-hash')+1])
                    window.inspection_roots=selection_roots(selected['paths'])
                    window.backup_path.set(selected['backup'])
                    window.quality.set(selected['quality'])
                    window.update_roots()
                except Exception as error:
                    messagebox.showerror('Não foi possível carregar a fila',str(error))
            if '--restaurar-admin' in sys.argv:
                window.after(300, window.restore)
        window.mainloop()
