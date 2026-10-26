import queue
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from inspection_queue import run_inspection_queue, selection_roots
from scan_index import analyze,find_plan,ScanCancelled


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.base=Path(self.temp.name)
        self.root=self.base/'raiz'; self.root.mkdir()
        for name,value in [('scan_index.cache_directory',self.base/'index')]:
            mock=patch(name,return_value=value);mock.start();self.addCleanup(mock.stop)
        for name in ['inspection.require_admin','inspection_queue.require_admin']:
            mock=patch(name);mock.start();self.addCleanup(mock.stop)
        mock=patch('inspection.ProcessPoolExecutor',side_effect=lambda **kw:ThreadPoolExecutor(max_workers=kw['max_workers']))
        mock.start();self.addCleanup(mock.stop)

    def tearDown(self): self.temp.cleanup()

    def photo(self,relative):
        source=self.root/relative;source.parent.mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(80,40),'red').save(source,format='HEIF')
        return source

    def test_single_scan_then_conversion_without_rescanning(self):
        source=self.photo('sub/foto.heic')
        (self.root/'vazia').mkdir()
        from scan_index import walk_folders
        with patch('scan_index.walk_folders',wraps=walk_folders) as scanner,patch('inspection.walk_folders',side_effect=AssertionError('Segunda varredura')):
            events=queue.Queue()
            run_inspection_queue([self.root],self.base/'backup',events,threading.Event())
        self.assertEqual(scanner.call_count,1)
        self.assertEqual(list(events.queue)[-1][1]['converted'],1)
        self.assertFalse(source.exists())
        self.assertEqual(find_plan(self.root).count(),0)

    def test_parent_preload_reused_for_subfolder_and_negative_subfolder(self):
        self.photo('com-heic/foto.heic'); empty=self.root/'sem-heic';empty.mkdir()
        analyze(self.root,queue.Queue(),threading.Event(),force=True)
        with patch('scan_index.walk_folders',side_effect=AssertionError('Não deve varrer')):
            plan=analyze(self.root/'com-heic',queue.Queue(),threading.Event())
            self.assertEqual(plan.count(),1)
            self.assertEqual(analyze(empty,queue.Queue(),threading.Event()).count(),0)
            events=queue.Queue()
            run_inspection_queue([self.root/'com-heic',empty],self.base/'backup',events,threading.Event())
        stats=list(events.queue)[-1][1]
        self.assertEqual(stats['converted'],1,stats)
        self.assertEqual(stats['skipped_roots'],[str(empty)])

    def test_cancel_never_publishes_partial_index_or_converts(self):
        source=self.photo('sub/foto.heic');stop=threading.Event()
        class Events(queue.Queue):
            def put(self,event):
                super().put(event)
                if event[0]=='analysis_progress': stop.set()
        events=Events()
        run_inspection_queue([self.root],self.base/'backup',events,stop)
        self.assertTrue(source.exists())
        self.assertFalse((self.base/'backup').exists())
        self.assertIsNone(find_plan(self.root))
        self.assertFalse(list((self.base/'index').glob('*.part')))
        self.assertTrue(list(events.queue)[-1][1]['cancelled'])

    def test_refresh_discovers_new_files_and_cancel_preserves_old_index(self):
        analyze(self.root,queue.Queue(),threading.Event(),force=True)
        self.photo('new/foto.heic')
        self.assertEqual(find_plan(self.root).count(),0)
        self.assertIsNone(find_plan(self.root/'new'))
        stop=threading.Event();stop.set()
        with self.assertRaises(ScanCancelled): analyze(self.root,queue.Queue(),stop,force=True)
        self.assertEqual(find_plan(self.root).count(),0)
        self.assertEqual(analyze(self.root,queue.Queue(),threading.Event(),force=True).count(),1)

    def test_missing_cached_file_is_reported_without_deleting_other_files(self):
        source=self.photo('sub/foto.heic')
        analyze(self.root,queue.Queue(),threading.Event())
        renamed=source.with_name('outra.heic');source.rename(renamed)
        before=renamed.read_bytes();events=queue.Queue()
        with patch('scan_index.walk_folders',side_effect=AssertionError('Varredura inesperada')):
            run_inspection_queue([self.root],self.base/'backup',events,threading.Event())
        stats=list(events.queue)[-1][1]
        self.assertEqual(stats['converted'],0)
        self.assertGreater(stats['errors'],0)
        self.assertEqual(renamed.read_bytes(),before)

    def test_selection_of_5000_paths_has_no_filesystem_calls(self):
        paths=[self.root/f'pasta-{i}' for i in range(5000)]
        with patch('pathlib.Path.stat',side_effect=AssertionError('Consulta de rede na seleção')),patch('pathlib.Path.resolve',side_effect=AssertionError('Resolve na seleção')):
            self.assertEqual(len(selection_roots(paths)),5000)
            self.assertEqual(selection_roots([*paths,self.root]),[self.root])


if __name__=='__main__': unittest.main()
