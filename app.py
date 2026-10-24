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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Conversor de fotos • HEIC para JPEG')
        self.resizable(False, False)
        self.configure(bg='#f3f5f8')
        self.paths = {}
        self.successes = {}
        self.converted_sizes = {}
        self.events = queue.Queue()
        self.busy = False
        self.accelerated = threading.Event()
        self.max_workers = min(4, os.cpu_count() or 1)
        self.active_rows = set()
        self.auto_select = tk.BooleanVar(value=False)
        self.quality = tk.StringVar(value='90')
        self.destination_mode = tk.StringVar(value='same')
        self.destination_path = tk.StringVar(value='')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background='#f3f5f8')
        style.configure('TLabel', background='#f3f5f8', font=('Segoe UI', 10))
        style.configure('Title.TLabel', font=('Segoe UI', 20, 'bold'), foreground='#162c48')
        style.configure('TButton', font=('Segoe UI', 10), padding=(12, 8))
        style.configure('TCheckbutton', background='#f3f5f8', font=('Segoe UI', 10))
        style.configure('TRadiobutton', background='#f3f5f8', font=('Segoe UI', 10))
        style.configure('Treeview', font=('Segoe UI', 10), rowheight=30)
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'))
        style.configure('Primary.TButton', background='#1b5ea8', foreground='white')
        style.map('Primary.TButton', background=[('active', '#154a85'), ('disabled', '#bcc9d8')])
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)
        ttk.Label(frame, text='Suas fotos, prontas para usar.', style='Title.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(frame, text='HEIC / HEIF → JPEG • conversão offline').grid(row=1, column=0, sticky='w', pady=(4, 12))
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=2, column=0, sticky='ew', pady=(0, 8))
        self.mutable = []
        for text, command in [('Adicionar fotos', self.add_files), ('Adicionar pasta', self.add_folder), ('Limpar lista', self.clear)]:
            button = ttk.Button(toolbar, text=text, command=command)
            button.pack(side='left', padx=(0, 8))
            self.mutable.append(button)
        ttk.Label(toolbar, text='Qualidade JPEG:').pack(side='left', padx=(12, 6))
        self.quality_box = ttk.Combobox(toolbar, textvariable=self.quality, values=[str(n) for n in range(10, 101, 5)], width=5)
        self.quality_box.pack(side='left')
        self.mutable.append(self.quality_box)
        ttk.Label(toolbar, text='(1–100)').pack(side='left', padx=(4, 0))
        destination = ttk.Frame(frame)
        destination.grid(row=3, column=0, sticky='ew', pady=(0, 8))
        destination.columnconfigure(3, weight=1)
        for column, text, value in [(0, 'Mesma pasta', 'same'), (1, 'Outra pasta', 'other')]:
            option = ttk.Radiobutton(destination, text=text, value=value, variable=self.destination_mode, command=self.update_destination)
            option.grid(row=0, column=column, sticky='w', padx=(0, 12))
            self.mutable.append(option)
        self.destination_button = ttk.Button(destination, text='Escolher pasta…', command=self.choose_destination, state='disabled')
        self.destination_button.grid(row=0, column=2, padx=(0, 8))
        self.destination_entry = ttk.Entry(destination, textvariable=self.destination_path, state='disabled', width=12)
        self.destination_entry.grid(row=0, column=3, sticky='ew')
        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, sticky='ew', pady=(0, 12))
        self.convert_button = ttk.Button(actions, text='Converter fotos', style='Primary.TButton', command=self.start, state='disabled')
        self.convert_button.pack(side='left', padx=(0, 8))
        self.accelerate_button = ttk.Button(actions, text='Ativar aceleração', command=self.toggle_acceleration)
        self.accelerate_button.pack(side='left', padx=(0, 10))
        self.mode_label = ttk.Label(actions, text='1 foto por vez')
        self.mode_label.pack(side='left')
        if self.max_workers == 1:
            self.accelerate_button.configure(state='disabled')
            self.mode_label.configure(text='1 processador disponível')
        table = ttk.Frame(frame)
        table.grid(row=5, column=0, sticky='nsew')
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=('file', 'status', 'original_size', 'jpeg_size', 'reduction', 'output'), show='headings', selectmode='extended', height=6)
        for name, title, width in [('file', 'Foto original', 185), ('status', 'Situação', 110), ('original_size', 'HEIC', 85), ('jpeg_size', 'JPEG', 85), ('reduction', 'Redução', 125), ('output', 'JPEG gerado / detalhe', 265)]:
            self.tree.heading(name, text=title)
            self.tree.column(name, width=width, minwidth=width, stretch=name == 'output')
        scroll = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        horizontal = ttk.Scrollbar(table, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scroll.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        self.tree.bind('<Double-1>', self.show_details)
        self.tree.tag_configure('ok', foreground='#146c43')
        self.tree.tag_configure('error', foreground='#b42318')
        ttk.Label(frame, text='Clique duas vezes em uma linha para ver os caminhos e detalhes.').grid(row=6, column=0, sticky='w', pady=(6, 8))
        self.check = ttk.Checkbutton(frame, text='Após converter, selecionar os HEICs convertidos no Explorador', variable=self.auto_select)
        self.check.grid(row=7, column=0, sticky='w')
        self.mutable.append(self.check)
        ttk.Label(frame, text='Os originais são mantidos. Você decide se deseja apagá-los no Explorador.').grid(row=8, column=0, sticky='w', pady=(4, 8))
        self.summary_label = ttk.Label(frame, text='O resumo de tamanho aparecerá ao terminar a conversão.', wraplength=900, foreground='#162c48')
        self.summary_label.grid(row=9, column=0, sticky='ew', pady=(0, 8))
        frame.bind('<Configure>', lambda event: self.summary_label.configure(wraplength=max(100, event.width - 32)))
        self.progress = ttk.Progressbar(frame, mode='determinate')
        self.progress.grid(row=10, column=0, sticky='ew')
        bottom = ttk.Frame(frame)
        bottom.grid(row=11, column=0, sticky='ew', pady=(8, 0))
        self.status = ttk.Label(bottom, text='Adicione fotos ou uma pasta para começar.')
        self.status.pack(side='left')
        self.select_button = ttk.Button(bottom, text='Selecionar originais no Explorador', command=self.select_originals, state='disabled')
        self.select_button.pack(side='right')
        self.fit_window()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)

    def update_destination(self):
        enabled = self.destination_mode.get() == 'other' and not self.busy
        self.destination_button.configure(state='normal' if enabled else 'disabled')
        self.destination_entry.configure(state='readonly' if enabled else 'disabled')

    def choose_destination(self):
        folder = filedialog.askdirectory(title='Escolher onde salvar os JPEGs')
        if folder:
            self.destination_path.set(str(Path(folder).resolve()))

    def update_summary(self):
        text = format_summary(self.converted_sizes.values())
        failures = sum(self.tree.set(row, 'status') == 'Falha' for row in self.paths)
        if failures:
            text += f'\n{failures} falha(s), fora dos totais.'
        self.summary_label.configure(text=text)

    def fit_window(self):
        self.update_idletasks()
        # Usa a área disponível, descontando a barra de tarefas e a moldura.
        import ctypes
        from ctypes import wintypes
        area = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(area), 0):
            left, top, right, bottom = area.left, area.top, area.right, area.bottom
        else:
            left, top, right, bottom = 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()
        width = min(max(1000, self.winfo_reqwidth()), right - left - 32)
        height = min(max(600, self.winfo_reqheight()), bottom - top - 64)
        self.geometry(f'{width}x{height}+{left + (right - left - width) // 2}+{top + (bottom - top - height) // 2}')

    def toggle_acceleration(self):
        if self.accelerated.is_set():
            self.accelerated.clear()
            self.accelerate_button.configure(text='Ativar aceleração')
            text = '1 foto por vez'
            if self.busy and len(self.active_rows) > 1:
                text += ' • concluindo as fotos em andamento'
        else:
            self.accelerated.set()
            self.accelerate_button.configure(text='Desativar aceleração')
            text = f'Até {self.max_workers} fotos ao mesmo tempo'
        self.mode_label.configure(text=text)

    def add_paths(self, paths):
        known = {str(p).casefold() for p in self.paths.values()}
        for path in paths:
            path = Path(path).resolve()
            key = str(path).casefold()
            if path.suffix.lower() in EXTENSIONS and key not in known:
                try:
                    size = path.stat().st_size
                except OSError:
                    size = None
                row = self.tree.insert('', 'end', values=(path.name, 'Aguardando', format_size(size), '—', '—', str(path.parent)))
                self.paths[row] = path
                known.add(key)
        self.status.configure(text=f'{len(self.paths)} foto(s) na lista.')
        self.refresh()

    def add_files(self):
        paths = filedialog.askopenfilenames(title='Selecionar fotos HEIC / HEIF', filetypes=[('Fotos HEIC / HEIF', '*.heic *.HEIC *.heif *.HEIF'), ('Todos os arquivos', '*.*')])
        self.add_paths(paths)

    def add_folder(self):
        folder = filedialog.askdirectory(title='Selecionar pasta com fotos HEIC / HEIF')
        if not folder:
            return
        try:
            paths = sorted(p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS)
            if not paths:
                messagebox.showinfo('Nenhuma foto', 'Esta pasta não contém fotos HEIC / HEIF. Subpastas não são incluídas.')
            self.add_paths(paths)
        except OSError as error:
            messagebox.showerror('Não foi possível ler a pasta', str(error))

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self.paths.clear()
        self.successes.clear()
        self.converted_sizes.clear()
        self.active_rows.clear()
        self.progress['value'] = 0
        self.status.configure(text='Adicione fotos ou uma pasta para começar.')
        self.summary_label.configure(text='O resumo de tamanho aparecerá ao terminar a conversão.')
        self.refresh()

    def refresh(self):
        pending = any(row not in self.successes for row in self.paths)
        self.convert_button.configure(state='normal' if pending and not self.busy else 'disabled')
        self.select_button.configure(state='normal' if self.successes and not self.busy else 'disabled')

    def start(self):
        work = [(row, path) for row, path in self.paths.items() if row not in self.successes]
        if not work or self.busy:
            return
        try:
            quality = int(self.quality.get())
            if not 1 <= quality <= 100:
                raise ValueError
        except ValueError:
            messagebox.showerror('Qualidade JPEG', 'Escolha ou digite um número inteiro de 1 a 100, por exemplo 75.')
            return
        output_folder = None
        if self.destination_mode.get() == 'other':
            folder = self.destination_path.get()
            if not folder or not Path(folder).is_dir():
                messagebox.showerror('Pasta de destino', 'Escolha uma pasta de destino disponível antes de converter.')
                return
            output_folder = Path(folder)
        self.busy = True
        self.active_rows.clear()
        for widget in self.mutable:
            widget.configure(state='disabled')
        self.update_destination()
        self.refresh()
        self.progress.configure(maximum=len(work), value=0)
        self.status.configure(text='Convertendo…')
        self.summary_label.configure(text='Calculando o resumo de tamanho…')
        threading.Thread(target=self.worker, args=(work, quality, output_folder), daemon=True).start()

    def worker(self, work, quality, output_folder=None):
        run_batch(work, quality, self.events, self.accelerated, self.max_workers, output_folder)

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == 'working':
                    self.active_rows.add(event[1])
                    self.tree.set(event[1], 'status', 'Convertendo…')
                elif kind in ('ok', 'error'):
                    row = event[1]
                    self.active_rows.discard(row)
                    if kind == 'ok':
                        self.successes[row] = (event[2], event[3])
                        self.converted_sizes[row] = (event[3][0], event[4])
                        self.tree.set(row, 'status', 'Convertida')
                        self.tree.set(row, 'original_size', format_size(event[3][0]))
                        self.tree.set(row, 'jpeg_size', format_size(event[4]))
                        self.tree.set(row, 'reduction', format_reduction(event[3][0], event[4]))
                    else:
                        self.tree.set(row, 'status', 'Falha')
                    self.tree.set(row, 'output', str(event[2]))
                    self.tree.item(row, tags=(kind,))
                    self.progress['value'] = float(self.progress['value']) + 1
                    self.status.configure(text=f'{int(float(self.progress["value"]))}/{int(float(self.progress["maximum"]))} concluída(s) • {len(self.active_rows)} em andamento')
                elif kind == 'done':
                    self.busy = False
                    self.active_rows.clear()
                    self.mode_label.configure(text=f'Até {self.max_workers} fotos ao mesmo tempo' if self.accelerated.is_set() else '1 foto por vez')
                    for widget in self.mutable:
                        widget.configure(state='normal')
                    self.update_destination()
                    self.update_summary()
                    failures = len(self.paths) - len(self.successes)
                    self.status.configure(text=f'{len(self.successes)} convertida(s) • {failures} falha(s).')
                    self.refresh()
                    if self.auto_select.get() and self.successes:
                        self.select_originals()
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def select_originals(self):
        valid = []
        for row, (jpeg, signature) in self.successes.items():
            source = self.paths[row]
            try:
                stat = source.stat()
                if (stat.st_size, stat.st_mtime_ns) == signature and jpeg.is_file() and jpeg.stat().st_size > 0:
                    valid.append(source)
            except OSError:
                pass
        if not valid:
            messagebox.showinfo('Nenhum original disponível', 'Os originais ou JPEGs não estão mais disponíveis, ou os originais foram alterados.')
            return
        try:
            select_files(valid)
        except Exception as error:
            messagebox.showerror('Explorador', str(error))

    def show_details(self, _event):
        rows = self.tree.selection()
        if rows:
            row = rows[0]
            messagebox.showinfo('Detalhes da foto', f'Original: {self.paths[row]}\n\nSituação: {self.tree.set(row, "status")}\n\nHEIC: {self.tree.set(row, "original_size")} • JPEG: {self.tree.set(row, "jpeg_size")}\nRedução: {self.tree.set(row, "reduction")}\n\n{self.tree.set(row, "output")}')

    def close(self):
        if self.busy:
            messagebox.showinfo('Conversão em andamento', 'Aguarde a conversão terminar antes de fechar o programa.')
        else:
            self.destroy()


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
        quality = int(sys.argv[3]) if len(sys.argv) == 5 else 90
        output_folder = Path(sys.argv[4]) if len(sys.argv) == 5 else None
        run_batch([(str(i), path) for i, path in enumerate(photos)], quality, events, accelerated, 2, output_folder)
        (folder / 'verificacao.json').write_text(json.dumps(list(events.queue), default=str, ensure_ascii=False), encoding='utf-8')
    else:
        App().mainloop()
