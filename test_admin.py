import queue
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import admin
import inspection
import os
import subprocess
import json


class AdminTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('HEIC_TEST_EXECUTABLE'), 'Requer executável gerado')
    def test_frozen_inspection_denied_without_admin(self):
        if admin.is_admin(): self.skipTest('Este teste verifica uma conta não elevada')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'root'; root.mkdir()
            source=root/'foto.heic'; source.write_bytes(b'unchanged')
            backup=Path(temporary)/'backup'; backup.mkdir()
            subprocess.run([os.environ['HEIC_TEST_EXECUTABLE'],'--verificar-vistorias',str(root),str(backup)],check=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
            events=json.loads((backup/'verificacao.json').read_text(encoding='utf-8'))
            self.assertEqual(events[0][0],'inspection_fatal')
            self.assertEqual(events[-1][1]['converted'],0)
            self.assertEqual(source.read_bytes(),b'unchanged')

    def test_permission_is_checked_without_launching_uac(self):
        with patch('admin.is_admin',return_value=False):
            with self.assertRaises(PermissionError): admin.require_admin()

    def test_no_file_is_changed_without_admin(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'root'; root.mkdir()
            source=root/'foto.heic'; source.write_bytes(b'preserve')
            backup=Path(temporary)/'backup'
            with patch('admin.is_admin',return_value=False):
                result=inspection.process_inspection_file(source,root,backup)
                self.assertEqual(result['status'],'error')
                events=queue.Queue()
                inspection.run_inspections(root,backup,events,threading.Event())
                self.assertEqual(list(events.queue)[0][0],'inspection_fatal')
                with self.assertRaises(PermissionError): inspection.restore_originals(backup)
            self.assertEqual(source.read_bytes(),b'preserve')
            self.assertFalse(backup.exists())

    def test_uac_uses_only_known_action_and_no_credentials(self):
        with patch.object(admin.ctypes.windll.shell32,'ShellExecuteW') as execute:
            execute.return_value=42
            admin.launch_admin()
            args=execute.call_args.args
            self.assertEqual(args[1],'runas')
            self.assertIn('--vistorias-admin',args[3])
            with self.assertRaises(ValueError): admin.launch_admin('--arbitrary')
            execute.return_value=5
            with self.assertRaises(PermissionError): admin.launch_admin()


if __name__=='__main__': unittest.main()
