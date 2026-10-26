import ctypes
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from app import App
from network_folders import normalize_location, server_only, list_folders, list_shares, FolderPicker
import gc


class NetworkFolderTests(unittest.TestCase):
    def test_server_and_unc_paths(self):
        self.assertEqual(normalize_location('SERVIDOR'),r'\\SERVIDOR')
        self.assertEqual(normalize_location(' //servidor/Vistorias/Sala '),r'\\servidor\Vistorias\Sala')
        self.assertTrue(server_only(r'\\servidor'))
        self.assertFalse(server_only(r'\\servidor\Vistorias'))
        self.assertEqual(normalize_location('C:/Fotos'),'C:\\Fotos')
        with self.assertRaises(ValueError): normalize_location('')
        with self.assertRaises(ValueError): normalize_location(r'\\?\C:\Fotos')

    def test_server_is_enumerated_without_scandir(self):
        with patch('network_folders.list_shares',return_value=[r'\\servidor\Vistorias']) as shares, patch('network_folders.os.scandir') as scan:
            self.assertEqual(list_folders(r'\\servidor'),[r'\\servidor\Vistorias'])
            shares.assert_called_once_with(r'\\servidor')
            scan.assert_not_called()

    def test_lists_only_subfolders(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'A').mkdir(); (root/'B').mkdir(); (root/'foto.jpg').write_bytes(b'unchanged')
            self.assertEqual(list_folders(str(root)),[str(root/'A'),str(root/'B')])

    def test_share_enumeration_filters_printers_and_frees_pages(self):
        from ctypes import wintypes
        class Share(ctypes.Structure):
            _fields_=[('name',wintypes.LPWSTR),('type',wintypes.DWORD),('remark',wintypes.LPWSTR)]
        pages=[(Share*2)(Share('Fotos',0,''),Share('Impressora',1,'')),(Share*1)(Share('Arquivo$',0x80000000,''))]
        api=Mock(); calls=[]
        def enum(server,level,buffer,size,count,total,resume):
            i=len(calls); calls.append(i)
            ctypes.cast(buffer,ctypes.POINTER(ctypes.c_void_p))[0]=ctypes.cast(pages[i],ctypes.c_void_p)
            ctypes.cast(count,ctypes.POINTER(wintypes.DWORD))[0]=len(pages[i])
            ctypes.cast(resume,ctypes.POINTER(wintypes.DWORD))[0]=i+1
            return 234 if i==0 else 0
        api.NetShareEnum.side_effect=enum
        with patch('network_folders.ctypes.WinDLL',return_value=api):
            self.assertEqual(list_shares(r'\\servidor'),[r'\\servidor\Arquivo$',r'\\servidor\Fotos'])
        self.assertEqual(api.NetApiBufferFree.call_count,2)

    def test_access_denied_is_reported(self):
        api=Mock(); api.NetShareEnum.return_value=5
        with patch('network_folders.ctypes.WinDLL',return_value=api):
            with self.assertRaises(OSError): list_shares(r'\\servidor')

    def test_picker_navigation_and_stale_response(self):
        app=App()
        try:
            picker=FolderPicker(app,'Teste')
            picker.after_cancel(picker.timer)
            picker.request_id=2
            picker.events.put((1,r'\\antigo',['old'],None))
            picker.events.put((2,r'\\servidor',[r'\\servidor\Fotos'],None))
            picker.poll()
            self.assertEqual(picker.current,r'\\servidor')
            self.assertEqual(picker.listbox.get(0),'Fotos')
            self.assertEqual(picker.choose.cget('state'),'disabled')
            picker.events.put((2,r'\\servidor\Fotos',[],None))
            picker.after_cancel(picker.timer)
            picker.poll()
            picker.location.set(r'\\servidor\Fotos')
            self.assertEqual(picker.choose.cget('state'),'normal')
            picker.accept()
            self.assertEqual(picker.result,r'\\servidor\Fotos')
        finally:
            if picker.winfo_exists(): picker.destroy()
            for timer in app.tk.call('after','info'): app.after_cancel(timer)
            app.destroy(); del app; gc.collect()


if __name__=='__main__': unittest.main()
