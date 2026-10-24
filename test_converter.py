import tempfile
import unittest
from pathlib import Path
from PIL import Image
from converter import convert_photo
from app import App
from batch import run_batch, format_reduction, format_summary, format_size
import queue
import threading
import gc
import os
import json
import subprocess
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def photo(self, name='Imóvel.HEIC'):
        path = self.folder / name
        image = Image.new('RGB', (80, 40), (180, 60, 30))
        exif = Image.Exif()
        exif[270] = 'Teste de imovel'
        image.save(path, format='HEIF', exif=exif)
        return path

    def test_real_heic_conversion_keeps_source_and_metadata(self):
        source = self.photo()
        before = source.read_bytes()
        output = convert_photo(source)
        self.assertEqual(output.parent, source.parent)
        self.assertEqual(output.suffix, '.jpg')
        self.assertEqual(source.read_bytes(), before)
        with Image.open(output) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertEqual(image.size, (80, 40))
            self.assertEqual(image.getexif()[270], 'Teste de imovel')

    def test_collision_preserves_existing_jpeg(self):
        source = self.photo()
        existing = source.with_suffix('.jpg')
        existing.write_bytes(b'arquivo existente')
        output = convert_photo(source)
        self.assertEqual(output.name, 'Imóvel (1).jpg')
        self.assertEqual(existing.read_bytes(), b'arquivo existente')

    def test_corrupt_heic_does_not_create_output(self):
        source = self.folder / 'invalida.heic'
        source.write_bytes(b'not an image')
        with self.assertRaises(Exception):
            convert_photo(source)
        self.assertTrue(source.exists())
        self.assertFalse(source.with_suffix('.jpg').exists())

    def test_alpha_is_composited_on_white(self):
        source = self.folder / 'alpha.heic'
        Image.new('RGBA', (20, 20), (0, 0, 0, 0)).save(source, format='HEIF')
        with Image.open(convert_photo(source)) as image:
            self.assertTrue(all(value >= 250 for value in image.getpixel((10, 10))))

    def test_rotated_heic_matches_decoded_orientation(self):
        source = self.folder / 'girada.heic'
        exif = Image.Exif()
        exif[274] = 6
        Image.new('RGB', (80, 40), 'red').save(source, format='HEIF', exif=exif)
        with Image.open(source) as image:
            expected_size = image.size
        with Image.open(convert_photo(source)) as image:
            self.assertEqual(image.size, expected_size)
            self.assertIn(image.getexif().get(274, 1), (1,))

    def test_interface_receives_results_and_skips_converted_files(self):
        app = App()
        app.withdraw()
        try:
            source = self.photo()
            app.add_paths([source, source])
            self.assertEqual(len(app.paths), 1)
            work = list(app.paths.items())
            app.worker(work, 90)
            app.poll()
            self.assertEqual(len(app.successes), 1)
            self.assertEqual(str(app.convert_button['state']), 'disabled')
            self.assertEqual(str(app.select_button['state']), 'normal')
            self.assertEqual(app.tree.set(work[0][0], 'reduction'), format_reduction(source.stat().st_size, next(iter(app.successes.values()))[0].stat().st_size))
            self.assertEqual(app.summary_label['text'], format_summary(app.converted_sizes.values()))
            app.deiconify()
            app.update()
            self.assertEqual(tuple(map(int, app.resizable())), (0, 0))
            self.assertLess(app.convert_button.winfo_rooty() + app.convert_button.winfo_height(), app.tree.winfo_rooty())
            self.assertLessEqual(app.select_button.winfo_rooty() + app.select_button.winfo_height(), app.winfo_rooty() + app.winfo_height())
            app.clear()
            self.assertEqual(len(app.paths), 0)
            self.assertEqual(len(app.converted_sizes), 0)
        finally:
            for timer in app.tk.call('after', 'info'):
                app.after_cancel(timer)
            app.destroy()
            del app
            gc.collect()

    def test_parallel_batch_real_heic_collision_and_isolated_failure(self):
        first = self.photo('mesmo.heic')
        second = self.photo('mesmo.heif')
        existing = self.folder / 'mesmo.jpg'
        existing.write_bytes(b'nao sobrescrever')
        bad = self.folder / 'erro.heic'
        bad.write_bytes(b'invalido')
        events = queue.Queue()
        accelerated = threading.Event()
        accelerated.set()
        run_batch([('a', first), ('b', second), ('c', bad)], 90, events, accelerated, 2)
        received = list(events.queue)
        successes = [event for event in received if event[0] == 'ok']
        self.assertEqual(len(successes), 2)
        self.assertEqual(len({event[2] for event in successes}), 2)
        self.assertEqual(existing.read_bytes(), b'nao sobrescrever')
        self.assertEqual([e[1] for e in received if e[0] == 'error'], ['c'])
        self.assertEqual(received[-1], ('done',))
        for event in successes:
            with Image.open(event[2]) as image:
                image.load()
                self.assertEqual(image.format, 'JPEG')

            self.assertEqual(event[4], event[2].stat().st_size)

    def test_live_acceleration_and_return_to_one_at_a_time(self):
        gates = {str(i): threading.Event() for i in range(4)}
        events = queue.Queue()
        accelerated = threading.Event()

        def held_job(path, quality, output_folder=None):
            if not gates[path].wait(5):
                raise TimeoutError('Teste não liberou a foto.')
            return Path(path + '.jpg'), (1000, 0), 500

        def thread_pool(**kwargs):
            return ThreadPoolExecutor(max_workers=kwargs['max_workers'])

        def expect(kind):
            event = events.get(timeout=3)
            self.assertEqual(event[0], kind)
            return event

        with patch('batch.ProcessPoolExecutor', side_effect=thread_pool), patch('batch.convert_job', side_effect=held_job):
            worker = threading.Thread(target=run_batch, args=([(str(i), str(i)) for i in range(4)], 90, events, accelerated, 3))
            worker.start()
            try:
                self.assertEqual(expect('working')[1], '0')
                with self.assertRaises(queue.Empty):
                    events.get(timeout=0.2)
                accelerated.set()
                self.assertEqual(expect('working')[1], '1')
                self.assertEqual(expect('working')[1], '2')
                accelerated.clear()
                for row in ['0', '1']:
                    gates[row].set()
                    self.assertEqual(expect('ok')[1], row)
                    with self.assertRaises(queue.Empty):
                        events.get(timeout=0.2)
                gates['2'].set()
                self.assertEqual(expect('ok')[1], '2')
                self.assertEqual(expect('working')[1], '3')
                gates['3'].set()
                self.assertEqual(expect('ok')[1], '3')
                expect('done')
            finally:
                for gate in gates.values():
                    gate.set()
                worker.join(timeout=6)
            self.assertFalse(worker.is_alive())

    def test_percentage_reduction_and_increase(self):
        self.assertEqual(format_reduction(1000, 600), '40,0%')
        self.assertEqual(format_reduction(1000, 1250), 'Aumento 25,0%')
        self.assertEqual(format_reduction(1000, 1000), '0,0%')
        self.assertEqual(format_reduction(0, 100), '—')

    def test_controls_visible_with_display_scaling(self):
        original_init = tk.Tk.__init__
        for scaling in [1.0, 2.0, 2.67]:
            def scaled_init(root, *args, **kwargs):
                original_init(root, *args, **kwargs)
                root.tk.call('tk', 'scaling', scaling)
            with self.subTest(scaling=scaling), patch.object(tk.Tk, '__init__', scaled_init):
                app = App()
                try:
                    app.update()
                    app.converted_sizes['example'] = (10000, 5000)
                    app.update_summary()
                    app.update()
                    for button in [app.convert_button, app.accelerate_button, app.select_button, app.destination_button, app.quality_box, app.summary_label]:
                        self.assertGreater(button.winfo_height(), 1)
                        self.assertGreaterEqual(button.winfo_rooty(), app.winfo_rooty())
                        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), app.winfo_rooty() + app.winfo_height())
                        self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), app.winfo_rootx() + app.winfo_width())
                finally:
                    for timer in app.tk.call('after', 'info'):
                        app.after_cancel(timer)
                    app.destroy()
                    del app
                    gc.collect()

    def test_quality_75_and_custom_folder_keep_originals(self):
        source = self.photo()
        destination = self.folder / 'JPEGs'
        destination.mkdir()
        output = convert_photo(source, 75, destination)
        self.assertEqual(output.parent, destination)
        self.assertFalse(source.with_suffix('.jpg').exists())
        self.assertTrue(source.exists())
        reference = self.folder / 'reference.jpg'
        Image.new('RGB', (80, 40), 'red').save(reference, quality=75)
        with Image.open(output) as actual, Image.open(reference) as expected:
            self.assertEqual(actual.quantization, expected.quantization)

    def test_parallel_common_destination_preserves_colliding_names(self):
        for folder in ['a', 'b', 'destino']:
            (self.folder / folder).mkdir()
        first = self.photo('a/foto.heic')
        second = self.photo('b/foto.heic')
        destination = self.folder / 'destino'
        existing = destination / 'foto.jpg'
        existing.write_bytes(b'preservado')
        events = queue.Queue()
        accelerated = threading.Event()
        accelerated.set()
        run_batch([('a', first), ('b', second)], 75, events, accelerated, 2, destination)
        successes = [e for e in events.queue if e[0] == 'ok']
        self.assertEqual(len(successes), 2, list(events.queue))
        self.assertEqual(len({e[2] for e in successes}), 2)
        self.assertTrue(all(e[2].parent == destination for e in successes))
        self.assertEqual(existing.read_bytes(), b'preservado')
        self.assertFalse(first.with_suffix('.jpg').exists())
        self.assertFalse(second.with_suffix('.jpg').exists())

    def test_total_summary_uses_sum_of_bytes_and_reports_increase(self):
        summary = format_summary([(1000, 100), (9000, 4500)])
        self.assertIn(f'HEIC {format_size(10000)} → JPEG {format_size(4600)}', summary)
        self.assertIn('redução de 54,0%', summary)
        self.assertIn('Aumento:', format_summary([(1000, 1500)]))
        self.assertIn('50,0%', format_summary([(1000, 1500)]))
        self.assertIn('Nenhuma foto convertida', format_summary([]))

    def test_invalid_settings_prevent_start_and_destination_can_be_reset(self):
        app = App()
        app.withdraw()
        try:
            app.add_paths([self.photo()])
            self.assertEqual(app.destination_mode.get(), 'same')
            self.assertIn('75', app.quality_box['values'])
            with patch('app.messagebox.showerror') as error:
                for quality in ['', 'abc', '0', '101', '75.5']:
                    app.quality.set(quality)
                    app.start()
                    self.assertFalse(app.busy)
                self.assertEqual(error.call_count, 5)
                app.quality.set('75')
                app.destination_mode.set('other')
                app.update_destination()
                self.assertEqual(str(app.destination_button['state']), 'normal')
                app.start()
                self.assertFalse(app.busy)
                self.assertEqual(error.call_count, 6)
            destination = self.folder / 'destino'
            destination.mkdir()
            with patch('app.filedialog.askdirectory', return_value=str(destination)):
                app.choose_destination()
            self.assertEqual(app.destination_path.get(), str(destination.resolve()))
            app.destination_mode.set('same')
            app.update_destination()
            self.assertEqual(str(app.destination_button['state']), 'disabled')
        finally:
            for timer in app.tk.call('after', 'info'):
                app.after_cancel(timer)
            app.destroy()
            del app
            gc.collect()

    def test_summary_excludes_failures_and_includes_previous_successes(self):
        app = App()
        app.withdraw()
        try:
            first = self.photo('boa.heic')
            invalid = self.folder / 'erro.heic'
            invalid.write_bytes(b'invalido')
            app.add_paths([first, invalid])
            app.worker(list(app.paths.items()), 75)
            app.poll()
            self.assertEqual(len(app.converted_sizes), 1)
            self.assertIn('1 falha(s), fora dos totais.', app.summary_label['text'])
            second = self.photo('segunda.heic')
            app.add_paths([second])
            pending = [(row, path) for row, path in app.paths.items() if row not in app.successes]
            app.worker(pending, 75)
            app.poll()
            self.assertEqual(len(app.converted_sizes), 2)
            self.assertIn('Total convertido (2 foto(s))', app.summary_label['text'])
        finally:
            for timer in app.tk.call('after', 'info'):
                app.after_cancel(timer)
            app.destroy()
            del app
            gc.collect()

    @unittest.skipUnless(os.environ.get('HEIC_TEST_EXECUTABLE'), 'Verificação opcional do executável gerado')
    def test_frozen_executable_workers(self):
        executable = Path(os.environ['HEIC_TEST_EXECUTABLE']).resolve()
        self.assertTrue(executable.is_file())
        first = self.photo('mesmo.heic')
        second = self.photo('mesmo.heif')
        existing = self.folder / 'mesmo.jpg'
        existing.write_bytes(b'nao sobrescrever')
        (self.folder / 'erro.heic').write_bytes(b'invalido')
        subprocess.run([str(executable), '--verificar-lote', str(self.folder)], check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        received = json.loads((self.folder / 'verificacao.json').read_text(encoding='utf-8'))
        successes = [event for event in received if event[0] == 'ok']
        self.assertEqual(len(successes), 2, received)
        self.assertEqual(len({event[2] for event in successes}), 2)
        self.assertEqual(sum(event[0] == 'error' for event in received), 1)
        self.assertEqual(received[-1], ['done'])
        self.assertEqual(existing.read_bytes(), b'nao sobrescrever')
        self.assertTrue(first.exists() and second.exists())
        for event in successes:
            with Image.open(event[2]) as image:
                image.load()
                self.assertEqual(image.format, 'JPEG')

        destination = self.folder / 'destino'
        destination.mkdir()
        collision = destination / 'mesmo.jpg'
        collision.write_bytes(b'preservado no destino')
        subprocess.run([str(executable), '--verificar-lote', str(self.folder), '75', str(destination)], check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        custom_received = json.loads((self.folder / 'verificacao.json').read_text(encoding='utf-8'))
        custom_successes = [event for event in custom_received if event[0] == 'ok']
        self.assertEqual(len(custom_successes), 2, custom_received)
        self.assertEqual(len({event[2] for event in custom_successes}), 2)
        self.assertEqual(collision.read_bytes(), b'preservado no destino')
        reference = self.folder / 'qualidade75.jpg'
        Image.new('RGB', (80, 40), 'red').save(reference, quality=75)
        for event in custom_successes:
            self.assertEqual(Path(event[2]).parent, destination)
            with Image.open(event[2]) as actual, Image.open(reference) as expected:
                self.assertEqual(actual.quantization, expected.quantization)


if __name__ == '__main__':
    unittest.main()
