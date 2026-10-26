import os
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import inspection
from safe_files import LockedFile, digest_file


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.auth = patch('inspection.require_admin')
        self.auth.start()
        self.addCleanup(self.auth.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base/'vistorias'
        self.root.mkdir()
        self.backup = self.base/'backup'
        self.root, self.namespace = inspection.prepare_locations(self.root,self.backup)

    def tearDown(self):
        self.temp.cleanup()

    def photo(self,name='foto.heic',multi=False):
        path=self.root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        image=Image.new('RGB',(80,40),'red')
        exif=Image.Exif(); exif[270]='Vistoria de teste'
        options=dict(save_all=True,append_images=[Image.new('RGB',(80,40),'blue')]) if multi else {}
        image.save(path,format='HEIF',exif=exif,**options)
        return path

    def convert(self,source):
        return inspection.process_inspection_file(source,self.root,self.namespace)

    def test_verified_removal_and_exact_restoration(self):
        source=self.photo(); original=source.read_bytes()
        result=self.convert(source)
        self.assertEqual(result['status'],'ok',result)
        self.assertFalse(source.exists())
        self.assertEqual(Path(result['backup']).read_bytes(),original)
        with Image.open(result['jpeg']) as image:
            image.load(); self.assertEqual(image.size,(80,40))
            self.assertEqual(image.getexif()[270],'Vistoria de teste')
        self.assertEqual(inspection.restore_originals(self.namespace),(1,0))
        self.assertEqual(source.read_bytes(),original)
        self.assertEqual(inspection.restore_originals(self.namespace),(0,1))

    def test_without_backup_validates_jpeg_and_does_not_copy_original(self):
        source=self.photo()
        with patch('inspection.copy_backup',side_effect=AssertionError('Não deve copiar')):
            result=inspection.process_inspection_file(source,self.root,self.namespace,75,False)
        self.assertEqual(result['status'],'ok',result)
        self.assertFalse(source.exists())
        self.assertEqual(result['backup'],'')
        self.assertFalse((self.namespace/'originais').exists())
        with Image.open(result['jpeg']) as image:
            image.load(); self.assertEqual(image.size,(80,40))
            self.assertEqual(image.getexif()[270],'Vistoria de teste')
        self.assertEqual(inspection.restore_originals(self.namespace),(0,0))
        with inspection.connect(self.namespace) as db:
            self.assertEqual(db.execute('SELECT state FROM jobs').fetchone()[0],'removed_no_backup')

    def test_without_backup_failures_preserve_source(self):
        for failure in ['encode','verify','journal']:
            with self.subTest(failure=failure):
                source=self.photo(failure+'.heic'); original=source.read_bytes()
                bad=self.root/'bad.jpg'; bad.write_bytes(b'broken')
                context=patch('inspection.convert_photo',side_effect=OSError('Disco cheio')) if failure=='encode' else patch('inspection.convert_photo',return_value=bad) if failure=='verify' else patch('inspection.connect',side_effect=OSError('Diário indisponível'))
                with context: result=inspection.process_inspection_file(source,self.root,self.namespace,75,False)
                self.assertEqual(result['status'],'error',result)
                self.assertEqual(source.read_bytes(),original)

    def test_without_backup_multiframe_preserved(self):
        source=self.photo(multi=True); original=source.read_bytes()
        result=inspection.process_inspection_file(source,self.root,self.namespace,75,False)
        self.assertEqual(result['status'],'retained',result)
        self.assertEqual(source.read_bytes(),original)

    def test_without_backup_commit_failure_preserves_source_after_jpeg(self):
        source=self.photo(); original=source.read_bytes()
        real=inspection.connect
        calls=0
        def fail_commit(namespace):
            nonlocal calls
            calls+=1
            if calls==2: raise OSError('Falha no diário antes da remoção')
            return real(namespace)
        with patch('inspection.connect',side_effect=fail_commit):
            result=inspection.process_inspection_file(source,self.root,self.namespace,75,False)
        self.assertEqual(result['status'],'error',result)
        self.assertTrue(Path(result['jpeg']).exists())
        self.assertEqual(source.read_bytes(),original)

    def test_corrupt_source_preserved(self):
        source=self.root/'bad.heic'; source.write_bytes(b'corrupt')
        result=self.convert(source)
        self.assertEqual(result['status'],'error')
        self.assertEqual(source.read_bytes(),b'corrupt')
        self.assertFalse(list(self.root.glob('*.jpg')))

    def test_multiple_images_are_retained(self):
        source=self.photo(multi=True)
        result=self.convert(source)
        self.assertEqual(result['status'],'retained',result)
        self.assertTrue(source.exists())

    def test_collision_preserved_and_correct_folder(self):
        for folder in ['a','b']:
            source=self.photo(folder+'/foto.heic')
            existing=source.with_suffix('.jpg'); existing.write_bytes(b'existing')
            result=self.convert(source)
            self.assertEqual(result['status'],'ok',result)
            self.assertEqual(Path(result['jpeg']).parent,source.parent)
            self.assertEqual(existing.read_bytes(),b'existing')

    def test_failed_backup_preserves_source(self):
        source=self.photo(); original=source.read_bytes()
        with patch('inspection.copy_backup',side_effect=OSError('Disco cheio')):
            self.assertEqual(self.convert(source)['status'],'error')
        self.assertEqual(source.read_bytes(),original)

    def test_failed_jpeg_preserves_source(self):
        source=self.photo(); original=source.read_bytes()
        with patch('inspection.convert_photo',side_effect=OSError('Disco cheio')):
            self.assertEqual(self.convert(source)['status'],'error')
        self.assertEqual(source.read_bytes(),original)

    def test_invalid_jpeg_preserves_source(self):
        source=self.photo()
        bad=self.root/'bad.jpg'; bad.write_bytes(b'broken')
        with patch('inspection.convert_photo',return_value=bad):
            self.assertEqual(self.convert(source)['status'],'error')
        self.assertTrue(source.exists())

    def test_journal_failure_preserves_source(self):
        source=self.photo()
        real=inspection.connect
        calls=0
        def failing(namespace):
            nonlocal calls
            calls+=1
            if calls==2: raise OSError('Falha no commit')
            return real(namespace)
        with patch('inspection.connect',side_effect=failing):
            self.assertEqual(self.convert(source)['status'],'error')
        self.assertTrue(source.exists())

    def test_restart_reuses_verified_jpeg(self):
        source=self.photo()
        with patch.object(LockedFile,'remove_on_close',side_effect=OSError('Interrupção')):
            result=self.convert(source)
        self.assertEqual(result['status'],'error',result)
        self.assertTrue(source.exists())
        self.assertEqual(len(list(self.root.glob('*.jpg'))),1)
        self.assertEqual(self.convert(source)['status'],'ok')
        self.assertEqual(len(list(self.root.glob('*.jpg'))),1)

    def test_corrupt_existing_backup_blocks_removal(self):
        source=self.photo()
        with patch.object(LockedFile,'remove_on_close',side_effect=OSError('Interrupção')):
            result=self.convert(source)
        Path(result['backup']).write_bytes(b'changed')
        self.assertEqual(self.convert(source)['status'],'error')
        self.assertTrue(source.exists())

    def test_restore_refuses_corrupt_backup(self):
        source=self.photo(); result=self.convert(source)
        self.assertEqual(result['status'],'ok',result)
        Path(result['backup']).write_bytes(b'changed')
        with self.assertRaises(ValueError): inspection.restore_originals(self.namespace)
        self.assertFalse(source.exists())

    def test_nested_backup_rejected(self):
        with self.assertRaises(ValueError): inspection.prepare_locations(self.root,self.root/'backup')
        with self.assertRaises(ValueError): inspection.prepare_locations(self.root,self.base)

    def test_only_one_run_uses_a_backup(self):
        with inspection.RunLock(self.namespace):
            with self.assertRaises(RuntimeError):
                with inspection.RunLock(self.namespace): pass

    def test_oriented_photo_is_validated(self):
        source=self.root/'orientada.heic'
        exif=Image.Exif(); exif[274]=6
        Image.new('RGB',(80,40),'green').save(source,format='HEIF',exif=exif)
        result=self.convert(source)
        self.assertEqual(result['status'],'ok',result)

    def test_fsync_failure_preserves_original(self):
        source=self.photo(); original=source.read_bytes()
        with patch('inspection.os.fsync',side_effect=OSError('Falha de gravação')):
            self.assertEqual(self.convert(source)['status'],'error')
        self.assertEqual(source.read_bytes(),original)

    def test_junction_does_not_escape_root(self):
        outside=self.base/'outside'; outside.mkdir()
        sentinel=outside/'foto.heic'; sentinel.write_bytes(b'preserved')
        junction=self.root/'atalho'
        import subprocess
        subprocess.run(['cmd','/c','mklink','/J',str(junction),str(outside)],check=True,capture_output=True)
        try:
            results=[]
            folders=list(inspection.walk_folders(self.root,threading.Event(),results.append))
            self.assertEqual(len(folders),1)
            self.assertEqual(results[0]['status'],'retained')
            self.assertEqual(sentinel.read_bytes(),b'preserved')
        finally:
            # Remove somente a junção criada neste teste; não recursa ao destino.
            junction.rmdir()

    def test_locked_original_preserved(self):
        source=self.photo()
        with LockedFile(source):
            self.assertEqual(self.convert(source)['status'],'error')
        self.assertTrue(source.exists())

    def test_hard_link_preserved(self):
        source=self.photo(); os.link(source,self.root/'other.heic')
        self.assertEqual(self.convert(source)['status'],'error')
        self.assertTrue(source.exists())

    def test_folder_barrier_and_report(self):
        sources=[self.photo(f'{folder}/{i}.heic') for folder in ['a','b'] for i in range(5)]
        events=queue.Queue(); stop=threading.Event()
        # Threads mantêm o mock de autorização; processos reais são testados no lote comum.
        with patch('inspection.ProcessPoolExecutor',side_effect=lambda **kw: ThreadPoolExecutor(max_workers=kw['max_workers'])):
            inspection.run_inspections(self.root,self.backup,events,stop,max_workers=4)
        received=list(events.queue)
        active=None; completed=0
        for event in received:
            if event[0]=='inspection_folder':
                self.assertIsNone(active); active=Path(event[1]); completed=0
            elif event[0]=='inspection_result':
                self.assertEqual(Path(event[1]['source']).parent,active)
                self.assertEqual(event[1]['status'],'ok',event[1]); completed+=1
            elif event[0]=='inspection_folder_done':
                self.assertEqual(completed,5); active=None
        stats=received[-1][1]
        self.assertEqual(stats['converted'],10,received)
        self.assertTrue(Path(stats['report']).is_file())
        self.assertFalse(any(s.exists() for s in sources))

    def test_cancel_finishes_active_folder_only(self):
        for folder in ['a','b']: self.photo(folder+'/foto.heic')
        stop=threading.Event(); events=queue.Queue()
        real=inspection.process_inspection_file
        def job(*args):
            result=real(*args); stop.set(); return result
        with patch('inspection.ProcessPoolExecutor',side_effect=lambda **kw: ThreadPoolExecutor(max_workers=kw['max_workers'])), patch('inspection.process_inspection_file',side_effect=job):
            inspection.run_inspections(self.root,self.backup,events,stop,max_workers=1)
        self.assertFalse((self.root/'a/foto.heic').exists())
        self.assertTrue((self.root/'b/foto.heic').exists())
        self.assertTrue(list(events.queue)[-1][1]['cancelled'])

    def test_thousands_of_empty_folders(self):
        for i in range(5001): (self.root/str(i)).mkdir()
        self.assertEqual(sum(1 for _ in inspection.walk_folders(self.root,threading.Event(),lambda r: None)),5002)


if __name__=='__main__': unittest.main()
