import ctypes
from ctypes import wintypes
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import tkinter as tk
import app  # Configura Tcl/Tk.
import windows_folders as folders


class WindowsFolderTests(unittest.TestCase):
    def test_network_places_round_trip_and_validation(self):
        places=[r'\\Servidor\Vistorias',r'\\Servidor\Fotos com espaço']
        self.assertEqual(folders.decode_places(folders.encode_places(places)),places)
        with self.assertRaises(ValueError): folders.decode_places(folders.encode_places(['C:\\']))
        with self.assertRaises(ValueError): folders.decode_places(folders.encode_places([r'\\?\C:\Fotos']))

    def test_default_picker_is_native(self):
        from network_folders import choose_directory
        parent=object()
        with patch('windows_folders.choose_native_folder',return_value='V:\\Vistorias') as native:
            self.assertEqual(choose_directory(parent,'Pasta','V:\\'),'V:\\Vistorias')
            native.assert_called_once_with(parent,'Pasta','V:\\')

    def test_elevation_passes_only_network_locations(self):
        import admin
        with patch('windows_folders.mapped_places',return_value=[r'\\Servidor\Fotos']), patch.object(admin.ctypes.windll.shell32,'ShellExecuteW') as execute:
            execute.return_value=42
            admin.launch_admin()
            args=execute.call_args.args[3]
            self.assertIn('--rede-origem',args)
            self.assertIn(folders.encode_places([r'\\Servidor\Fotos']),args)

    def native_dialog(self,select,multiple=False):
        user=ctypes.WinDLL('user32')
        kernel=ctypes.WinDLL('kernel32')
        callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
        user.EnumThreadWindows.argtypes=[wintypes.DWORD,callback_type,wintypes.LPARAM]
        user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
        user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        thread_id=kernel.GetCurrentThreadId()
        root=tk.Tk(); root.withdraw()
        stop=threading.Event(); observed=[]
        title='HEICLite - teste automatizado de seletor'
        def dismiss():
            first=None
            @callback_type
            def visit(window,param):
                nonlocal first
                name=ctypes.create_unicode_buffer(256)
                user.GetWindowTextW(window,name,256)
                if name.value==title:
                    observed.append(True)
                    if first is None:
                        first=time.monotonic()
                        user.PostMessageW(window,0x111,1,0) if select else user.PostMessageW(window,0x10,0,0)
                    elif time.monotonic()-first>2:
                        user.PostMessageW(window,0x10,0,0)
                return True
            while not stop.wait(.05): user.EnumThreadWindows(thread_id,visit,0)
        helper=threading.Thread(target=dismiss,daemon=True); helper.start()
        try:
            with tempfile.TemporaryDirectory() as path:
                result=folders.choose_native_folder(root,title,path,multiple=multiple)
                self.assertTrue(observed)
                self.assertEqual(result,[path] if select and multiple else [] if multiple else path if select else '')
        finally:
            stop.set(); helper.join(2); root.destroy()

    def test_real_native_dialog_cancel(self): self.native_dialog(False)
    def test_real_native_dialog_select_folder(self): self.native_dialog(True)
    def test_real_native_dialog_multiselect_result_array(self): self.native_dialog(True,True)
    def test_real_native_dialog_cancel_multiple(self): self.native_dialog(False,True)


if __name__=='__main__': unittest.main()
