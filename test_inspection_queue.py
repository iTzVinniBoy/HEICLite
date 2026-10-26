import csv
import queue
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from inspection import restore_originals
from inspection_queue import normalize_roots,prepare_queue,run_inspection_queue


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        cache=patch('scan_index.cache_directory',return_value=self.base/'index'); cache.start(); self.addCleanup(cache.stop)
        self.roots=[self.base/'A',self.base/'B']
        for root in self.roots: root.mkdir()
        self.backup=self.base/'backup'
        for name in ['inspection.require_admin','inspection_queue.require_admin']:
            auth=patch(name); auth.start(); self.addCleanup(auth.stop)
        pool=patch('inspection.ProcessPoolExecutor',side_effect=lambda **kw:ThreadPoolExecutor(max_workers=kw['max_workers']))
        pool.start(); self.addCleanup(pool.stop)

    def tearDown(self): self.temp.cleanup()

    def photos(self):
        originals={}
        for root in self.roots:
            sub=root/'sala'; sub.mkdir()
            path=sub/'foto.heic'
            Image.new('RGB',(80,40),'red').save(path,format='HEIF')
            originals[path]=path.read_bytes()
        return originals

    def test_parent_child_and_duplicates_removed(self):
        child=self.roots[0]/'sala'; child.mkdir()
        self.assertEqual(normalize_roots([child,self.roots[0],self.roots[0],self.roots[1]]),self.roots)
        self.assertEqual(normalize_roots([self.roots[0],child]),[self.roots[0]])

    def test_without_backup_queue_writes_only_local_reports(self):
        originals=self.photos()
        reports=self.base/'local-reports'
        events=queue.Queue()
        with patch('inspection_queue.report_directory',return_value=reports), patch('inspection.copy_backup',side_effect=AssertionError('Backup desativado')):
            run_inspection_queue(self.roots,'',events,threading.Event(),75,4,False)
        stats=list(events.queue)[-1][1]
        self.assertEqual(stats['converted'],2,stats)
        self.assertFalse(stats['backup_enabled'])
        self.assertFalse(self.backup.exists())
        self.assertTrue(Path(stats['report']).is_file())
        self.assertFalse(list(reports.rglob('*.heic')))
        self.assertFalse(list(reports.rglob('originais')))
        for source in originals:
            self.assertFalse(source.exists())
            self.assertTrue(source.with_suffix('.jpg').exists())

    def test_only_other_formats_creates_no_backup(self):
        sub=self.roots[0]/'sub'; sub.mkdir()
        photo=sub/'foto.jpg'; photo.write_bytes(b'original jpg')
        events=queue.Queue()
        run_inspection_queue(self.roots,self.backup,events,threading.Event())
        stats=list(events.queue)[-1][1]
        self.assertEqual(stats['converted'],0)
        self.assertEqual(stats['skipped_roots'],list(map(str,self.roots)))
        self.assertEqual(stats['reports'],[])
        self.assertFalse(self.backup.exists())
        self.assertEqual(photo.read_bytes(),b'original jpg')

    def test_mixed_tree_converts_nested_heic_only(self):
        parent=self.roots[0]
        (parent/'foto.jpg').write_bytes(b'keep jpg')
        sub=parent/'heics'; sub.mkdir()
        source=sub/'foto.HEIC'
        Image.new('RGB',(80,40),'red').save(source,format='HEIF')
        original=source.read_bytes()
        (sub/'outra.png').write_bytes(b'keep png')
        empty=parent/'somente jpg'; empty.mkdir()
        (empty/'outra.jpg').write_bytes(b'keep another')
        events=queue.Queue()
        run_inspection_queue(self.roots,self.backup,events,threading.Event())
        stats=list(events.queue)[-1][1]
        self.assertEqual(stats['converted'],1)
        self.assertEqual(stats['skipped_roots'],[str(self.roots[1])])
        namespaces=[p for p in self.backup.iterdir() if p.is_dir()]
        self.assertEqual(len(namespaces),1)
        self.assertFalse(any(p.name=='somente jpg' for p in namespaces[0].rglob('*')))
        self.assertEqual((parent/'foto.jpg').read_bytes(),b'keep jpg')
        self.assertEqual((sub/'outra.png').read_bytes(),b'keep png')
        self.assertEqual(restore_originals(namespaces[0]),(1,0))
        self.assertEqual(source.read_bytes(),original)

    def test_scan_error_not_reported_as_empty_success(self):
        def inaccessible(root,stop,notify):
            notify(dict(source=str(root),status='error',detail='Acesso negado'))
            return iter(())
        events=queue.Queue()
        with patch('scan_index.walk_folders',side_effect=inaccessible):
            run_inspection_queue(self.roots,self.backup,events,threading.Event())
        self.assertEqual(list(events.queue)[-1][1]['errors'],2)
        self.assertFalse(self.backup.exists())

    def test_backup_checked_against_all_roots_before_conversion(self):
        originals=self.photos()
        events=queue.Queue()
        run_inspection_queue(self.roots,self.roots[1]/'backup',events,threading.Event())
        self.assertEqual(list(events.queue)[0][0],'inspection_fatal')
        self.assertFalse((self.roots[1]/'backup').exists())
        for source,data in originals.items(): self.assertEqual(source.read_bytes(),data)

    def test_multiple_roots_cumulative_totals_and_restore(self):
        originals=self.photos()
        events=queue.Queue()
        run_inspection_queue(self.roots,self.backup,events,threading.Event())
        received=list(events.queue)
        progress=[e[1:] for e in received if e[0]=='inspection_progress']
        self.assertEqual(progress,[(0,2),(1,2),(2,2)])
        self.assertEqual(sum(e[0]=='inspection_done' for e in received),1)
        results=[e for e in received if e[0]=='inspection_result']
        self.assertEqual([e[2]['converted'] for e in results],[1,2])
        root_events=[i for i,e in enumerate(received) if e[0]=='inspection_root']
        first_finished=next(i for i,e in enumerate(received) if e[0]=='inspection_result')
        self.assertLess(first_finished,root_events[1])
        stats=received[-1][1]
        self.assertEqual(stats['converted'],2)
        self.assertEqual(stats['completed_roots'],2)
        self.assertEqual(stats['before'],sum(len(b) for b in originals.values()))
        with Path(stats['report']).open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.reader(stream,delimiter=';'))
        self.assertEqual(len(rows),3)
        _,namespaces=prepare_queue(self.roots,self.backup)
        self.assertEqual(len(set(namespaces)),2)
        for namespace in namespaces: self.assertEqual(restore_originals(namespace),(1,0))
        for source,data in originals.items(): self.assertEqual(source.read_bytes(),data)

    def test_stop_does_not_start_next_root(self):
        originals=self.photos()
        stop=threading.Event()
        class Events(queue.Queue):
            def put(self,event):
                super().put(event)
                if event[0]=='inspection_result': stop.set()
        events=Events()
        run_inspection_queue(self.roots,self.backup,events,stop)
        self.assertTrue(list(events.queue)[-1][1]['cancelled'])
        second=next(p for p in originals if self.roots[1] in p.parents)
        self.assertEqual(second.read_bytes(),originals[second])
        self.assertEqual(sum(e[0]=='inspection_root' for e in events.queue),1)

    def test_fatal_error_stops_later_roots(self):
        self.photos()
        events=queue.Queue()
        with patch('inspection.RunLock',side_effect=RuntimeError('Backup ocupado')):
            run_inspection_queue(self.roots,self.backup,events,threading.Event())
        self.assertEqual(sum(e[0]=='inspection_root' for e in events.queue),1)
        self.assertTrue(list(events.queue)[-1][1]['failed'])


if __name__=='__main__': unittest.main()
