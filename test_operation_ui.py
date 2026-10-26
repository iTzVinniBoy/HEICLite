import gc
import tempfile
import unittest
import threading
from pathlib import Path
from unittest.mock import patch
from app import App
from batch import format_size
from operation_history import History


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)

    def tearDown(self): self.temp.cleanup()

    def app(self):
        app = App(); app.withdraw()
        app.history = History(self.base/'history.sqlite3')
        def cleanup():
            for timer in app.tk.call('after','info'): app.after_cancel(timer)
            app.destroy(); gc.collect()
        self.addCleanup(cleanup)
        return app

    def test_compact_decimal_units(self):
        self.assertEqual(format_size(2860810000), '2,86 GB')
        self.assertEqual(format_size(950000000), '950 MB')
        self.assertEqual(format_size(1000000000000), '1 TB')
        self.assertEqual(format_size(0), '0 B')

    def test_switch_preserves_both_modules_results_and_timing(self):
        app = self.app()
        source = self.base/'photo.heic'; source.write_bytes(b'fake')
        app.add_paths([source]); row = next(iter(app.paths))
        app.tree.set(row,'status','Convertida')
        app.successes[row]=(self.base/'photo.jpg',(4,0))
        app.converted_sizes[row]=(4,2); app.update_summary()
        app.elapsed=65; app.set_progress(1); app.status.configure(text='Fotos terminadas')
        with patch('ui.is_admin',return_value=True): app.switch_mode('Vistorias')
        self.assertFalse(app.paths)
        batch_row = app.tree.insert('','end',values=('vistoria.heic','Conferida'))
        app.details[batch_row]={'source':'vistoria.heic'}
        app.elapsed=125; app.set_progress(.5); app.last_report='test.csv'
        app.switch_mode('Fotos')
        self.assertEqual(app.paths[row],source)
        self.assertEqual(app.tree.set(row,'status'),'Convertida')
        self.assertEqual(app.elapsed,65)
        self.assertEqual(app.progress.get(),1)
        with patch('ui.is_admin',return_value=True): app.switch_mode('Vistorias')
        self.assertIn(batch_row,app.details)
        self.assertEqual(app.last_report,'test.csv')
        self.assertEqual(app.elapsed,125)
        self.assertEqual(app.progress.get(),.5)

    def test_destination_required_and_same_source_rejected(self):
        app=self.app()
        source=self.base/'photo.heic'; source.write_bytes(b'fake')
        app.add_paths([source])
        with patch('ui.messagebox.showerror') as error, patch('ui.threading.Thread') as thread:
            app.start()
            app.destination_path.set(str(self.base)); app.start()
            self.assertEqual(error.call_count,2)
            thread.assert_not_called()
        self.assertFalse(app.busy)

    def test_slow_network_selection_does_not_block_ui(self):
        app=self.app(); release=threading.Event(); ticks=[]
        folder=self.base/'servidor';folder.mkdir()
        actual=Path.is_dir
        def slow(path):
            if path==folder: release.wait(3)
            return actual(path)
        with patch('pathlib.Path.is_dir',slow):
            app.receive_folders([str(folder)])
            app.after(30,lambda:ticks.append(not release.is_set()))
            app.after(100,release.set)
            app.after(450,app.quit)
            app.mainloop()
        self.assertEqual(ticks,[True])
        self.assertEqual(app.inspection_roots,[folder])
        self.assertFalse(app.busy)

    def test_backup_default_and_explicit_no_backup_confirmation(self):
        app=self.app()
        self.assertTrue(app.backup_enabled.get())
        with patch('ui.is_admin',return_value=True):
            app.switch_mode('Vistorias')
            app.inspection_roots=[self.base]
            app.backup_enabled.set(False); app.update_backup_controls()
            self.assertTrue(all(widget.cget('state')=='disabled' for widget in app.backup_controls))
            self.assertIn('SEM BACKUP',app.destination_label.cget('text'))
            with patch('ui.messagebox.askyesno',return_value=False) as confirm, patch('ui.threading.Thread') as thread:
                app.start()
                self.assertIn('SEM BACKUP',confirm.call_args.args[1])
                self.assertEqual(confirm.call_args.kwargs['default'],'no')
                thread.assert_not_called()
        self.assertFalse(app.busy)

    def test_history_persists_actual_folder_results_and_elapsed(self):
        app=self.app()
        with patch('ui.time.monotonic',return_value=100): app.begin_operation([str(self.base)])
        app.record_result(self.base/'sub'/'one.heic',True,2000,1000)
        app.record_result(self.base/'sub'/'two.heic',False,0,0)
        with patch('ui.time.monotonic',return_value=165): app.finish_operation('Concluído com falhas')
        entry=History(app.history.path).list()[0]
        self.assertEqual(entry['elapsed'],65)
        result=entry['folders'][str(self.base/'sub')]
        self.assertEqual((result['converted'],result['errors'],result['before'],result['after']),(1,1,2000,1000))
        self.assertEqual(entry['status'],'Concluído com falhas')
        app.poll()
        self.assertEqual(app.elapsed,65)

    def test_cancelled_inspection_keeps_percentage_and_time(self):
        app=self.app()
        with patch('ui.is_admin',return_value=True): app.switch_mode('Vistorias')
        app.begin_operation([str(self.base)])
        app.set_busy(True)
        app.events.put(('inspection_progress',3,10))
        app.events.put(('inspection_done',dict(cancelled=True,converted=3,before=300,after=100,visited=1,errors=0,retained=0)))
        app.poll()
        self.assertEqual(app.progress.get(),.3)
        self.assertFalse(app.busy)
        self.assertEqual(app.history.list()[0]['status'],'Interrompido')

    def test_history_incomplete_run_is_not_claimed_complete(self):
        history=History(self.base/'history.sqlite3')
        history.start(dict(mode='Vistorias',status='Iniciada • sem registro de conclusão'))
        self.assertIn('sem registro de conclusão',History(history.path).list()[0]['status'])


if __name__=='__main__': unittest.main()
