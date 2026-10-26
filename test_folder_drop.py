import ctypes
from ctypes import wintypes
import gc
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import App
from queue_handoff import create_handoff,read_handoff


class FolderDropTests(unittest.TestCase):
    def test_loose_photos_and_folders_in_both_windows_only_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            photo=root/'foto.HEIC'; photo.write_bytes(b'synthetic placeholder')
            other=root/'foto.jpg'; other.write_bytes(b'unchanged')
            folder=root/'Vistoria'; folder.mkdir()
            for elevated in (False,True):
                with self.subTest(elevated=elevated), patch('ui.is_admin',return_value=elevated):
                    app=App()
                    try:
                        self.assertIsNotNone(app.folder_drop)
                        self.assertEqual(app.folder_drop.elevated,elevated)
                        with patch.object(app,'start') as start:
                            app.receive_folders([str(photo),str(other),str(folder)])
                            app.after(350,app.quit); app.mainloop()
                            self.assertEqual(list(app.paths.values()),[photo])
                            self.assertEqual(app.inspection_roots,[folder])
                            self.assertFalse(app.busy)
                            start.assert_not_called()
                        app.receive_folders([str(photo)])
                        app.after(350,app.quit); app.mainloop()
                        self.assertEqual(len(app.paths),1)
                        self.assertEqual(other.read_bytes(),b'unchanged')
                        if elevated:
                            app.switch_mode('Vistorias'); app.update()
                            self.assertTrue(app.drop_area.winfo_viewable())
                            app.receive_folders([str(photo)])
                            app.after(350,app.quit); app.mainloop()
                            self.assertFalse(app.paths)
                            self.assertIn('fotos soltas',app.status.cget('text'))
                    finally:
                        for timer in app.tk.call('after','info'): app.after_cancel(timer)
                        app.destroy(); del app; gc.collect()

    def test_handoff_and_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'Vistoria'; folder.mkdir()
            path,checksum=create_handoff([folder],str(Path(temp)/'backup'))
            try:
                self.assertEqual(read_handoff(path,checksum)['paths'],[str(folder)])
                Path(path).write_bytes(b'alterado')
                with self.assertRaises(ValueError): read_handoff(path,checksum)
            finally: Path(path).unlink(missing_ok=True)

    def test_real_windows_drop_queues_folders_and_handoff(self):
        with tempfile.TemporaryDirectory() as temp:
            paths=[Path(temp)/'Pasta A',Path(temp)/'Pasta B']
            for path in paths: path.mkdir()
            with patch('ui.is_admin',return_value=False): app=App()
            try:
                self.assertIsNotNone(app.folder_drop)
                app.update()
                self.assertIn(app.drop_area.winfo_id(),app.folder_drop.handles)
                self.assertIn(app.drop_label.winfo_id(),app.folder_drop.handles)
                data=struct.pack('<IiiII',20,0,0,0,1)+('\0'.join(str(p) for p in paths)+'\0\0').encode('utf-16-le')
                kernel=ctypes.WinDLL('kernel32')
                kernel.GlobalAlloc.argtypes=[wintypes.UINT,ctypes.c_size_t]; kernel.GlobalAlloc.restype=wintypes.HGLOBAL
                kernel.GlobalLock.argtypes=[wintypes.HGLOBAL]; kernel.GlobalLock.restype=ctypes.c_void_p
                kernel.GlobalUnlock.argtypes=[wintypes.HGLOBAL]
                handle=kernel.GlobalAlloc(2,len(data))
                address=kernel.GlobalLock(handle)
                ctypes.memmove(address,data,len(data)); kernel.GlobalUnlock(handle)
                user=ctypes.WinDLL('user32')
                user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
                # Entrega ao rótulo sob o mouse, não artificialmente à janela pai.
                user.PostMessageW(app.drop_label.winfo_id(),0x233,handle,0)
                # Como o Explorer: a mensagem chega durante mainloop, sem uma
                # chamada Python síncrona ao SendMessage protegendo o estado Tk.
                app.after(250,app.quit)
                app.mainloop()
                self.assertEqual(app.inspection_roots,paths)
                with patch('ui.launch_admin') as launch:
                    app.elevate('--vistorias-admin')
                    self.assertEqual(launch.call_args.kwargs['folders'],paths)
                app.busy=True
                extra=Path(temp)/'C'; extra.mkdir()
                app.receive_folders([str(extra)])
                self.assertEqual(app.inspection_roots,paths)
            finally:
                for timer in app.tk.call('after','info'): app.after_cancel(timer)
                app.destroy(); del app; gc.collect()


if __name__=='__main__': unittest.main()
