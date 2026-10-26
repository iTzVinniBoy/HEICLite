"""Interface desktop do HEICLite."""
import os
import queue
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk
from PIL import Image
from version import APP_VERSION
from converter import EXTENSIONS
from batch import run_batch, format_size, format_reduction, format_summary
from inspection import run_inspections, restore_originals, prepare_locations
from operation_history import History
from window_theme import apply_titlebar, ThemedToplevel
from admin import is_admin, launch_admin
from network_folders import choose_directory
from windows_folders import choose_native_folder
from inspection_queue import normalize_roots, selection_roots, validate_queue, run_inspection_queue, preload_roots, report_directory


class App(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode('system')
        ctk.set_default_color_theme('blue')
        super().__init__()
        self.title('HEICLite • Administrador' if is_admin() else 'HEICLite • Fotos prontas, arquivos protegidos')
        width, height = min(1180, self.winfo_screenwidth()-60), min(760, self.winfo_screenheight()-100)
        self.geometry(f'{width}x{height}')
        self.minsize(min(940, width), min(600, height))
        self.configure(fg_color=('#eef2f9', '#101321'))
        self.paths, self.successes, self.converted_sizes, self.details = {}, {}, {}, {}
        self.events = queue.Queue()
        self.accelerated, self.stop = threading.Event(), threading.Event()
        self.accelerated.set()
        self.max_workers = min(4, os.cpu_count() or 1)
        self.busy = False
        self.mode = 'Fotos'
        self.quality = tk.StringVar(value='75')
        self.destination_mode = tk.StringVar(value='other')
        self.views = {}
        self.started_at = None
        self.elapsed = 0
        self.history = History()
        self.history_id = None
        self.run_data = {}
        self.progress_text = '0%'
        self.destination_path = tk.StringVar()
        self.root_path, self.backup_path = tk.StringVar(), tk.StringVar()
        self.backup_enabled = tk.BooleanVar(value=True)
        self.backup_controls = []
        self.use_index=tk.BooleanVar(value=True)
        self.analysis_dialog=None
        self.phase=None
        self.inspection_roots = []
        self.last_report = None
        self.mutable = []
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        side = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color=('#ffffff', '#191d31'))
        side.grid(row=0, column=0, sticky='nsew')
        side.grid_propagate(False)
        assets = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'assets'
        self.logo = ctk.CTkImage(Image.open(assets/'heiclite.png'), size=(56, 56))
        ctk.CTkLabel(side, text='', image=self.logo).pack(pady=(28, 6))
        ctk.CTkLabel(side, text='HEICLite', font=('Segoe UI', 25, 'bold')).pack()
        ctk.CTkLabel(side, text='Menos espaço. Mais clareza.', text_color=('#65738c', '#a2adc7'), font=('Segoe UI', 11)).pack(pady=(0, 30))
        for mode, title in [('Fotos', '▧   Converter fotos'), ('Vistorias', '▤   Vistorias em lote')]:
            self.button(side, title, lambda m=mode: self.switch_mode(m)).pack(fill='x', padx=16, pady=5)
        self.button(side, '↺   Restaurar originais', self.restore).pack(fill='x', padx=16, pady=(24, 5))
        self.version_label = ctk.CTkLabel(side, text=f'Versão {APP_VERSION}', font=('Segoe UI', 11), text_color=('#65738c', '#a2adc7'))
        self.version_label.pack(side='bottom', pady=(0, 12))
        ctk.CTkLabel(side, text='APARÊNCIA', font=('Segoe UI', 10, 'bold'), text_color=('#65738c', '#a2adc7')).pack(side='bottom', pady=(10, 5))
        ctk.CTkOptionMenu(side, values=['Automático', 'Claro', 'Escuro'], command=self.set_theme, width=178).pack(side='bottom', padx=16, pady=(0, 20))
        self.button(side, '◷   Histórico', self.show_history).pack(fill='x', padx=16, pady=5)

        body = ctk.CTkFrame(self, fg_color='transparent')
        body.grid(row=0, column=1, sticky='nsew', padx=24, pady=20)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(4, weight=1)
        self.heading = ctk.CTkLabel(body, text='Suas fotos, em JPEG.', font=('Segoe UI', 27, 'bold'), anchor='w')
        self.heading.grid(row=0, column=0, sticky='ew')
        self.subtitle = ctk.CTkLabel(body, text='Converta com rapidez e mantenha os originais.', anchor='w', text_color=('#65738c', '#a2adc7'))
        self.subtitle.grid(row=1, column=0, sticky='ew', pady=(0, 16))
        cards = ctk.CTkFrame(body, fg_color='transparent')
        cards.grid(row=2, column=0, sticky='ew', pady=(0, 16))
        self.cards = []
        for i, title in enumerate(['CONVERTIDAS', 'HEIC ORIGINAL', 'JPEG GERADO', 'REDUÇÃO']):
            cards.grid_columnconfigure(i, weight=1)
            card = ctk.CTkFrame(cards, corner_radius=14, fg_color=('#ffffff', '#20253c'))
            card.grid(row=0, column=i, sticky='ew', padx=(0, 10 if i<3 else 0))
            ctk.CTkLabel(card, text=title, font=('Segoe UI', 10, 'bold'), text_color=('#65738c', '#a2adc7')).pack(anchor='w', padx=15, pady=(12, 0))
            label = ctk.CTkLabel(card, text='—', font=('Segoe UI', 22, 'bold'))
            label.pack(anchor='w', padx=15, pady=(0, 12))
            self.cards.append(label)
        controls = ctk.CTkFrame(body, corner_radius=14, fg_color=('#ffffff', '#20253c'))
        controls.grid(row=3, column=0, sticky='ew', pady=(0, 12))
        controls.grid_columnconfigure(0, weight=1)
        self.options = ctk.CTkFrame(controls, fg_color='transparent')
        self.options.grid(row=0, column=0, sticky='ew', padx=12, pady=10)
        self.options.grid_columnconfigure(1, weight=1)
        self.normal = ctk.CTkFrame(self.options, fg_color='transparent')
        self.normal.grid(row=0, column=0, columnspan=3, sticky='ew')
        self.button(self.normal, '+ Fotos', self.choose_files).pack(side='left', padx=(0, 6))
        self.button(self.normal, '+ Pasta', self.choose_folder).pack(side='left', padx=6)
        self.button(self.normal, 'Limpar', self.clear).pack(side='left', padx=6)
        self.destination_button = self.button(self.normal, 'Escolher destino…', self.choose_destination, primary=True)
        self.destination_button.pack(side='left', padx=6)
        self.inspection_controls = ctk.CTkFrame(self.options, fg_color='transparent')
        self.inspection_controls.grid_columnconfigure(1, weight=1)
        for i, (label, variable) in enumerate([('Adicionar pastas', self.root_path), ('Backup dos HEICs', self.backup_path)]):
            picker=self.button(self.inspection_controls, label, lambda v=variable: self.choose_path(v))
            picker.grid(row=i, column=0, padx=(0, 8), pady=3)
            entry = ctk.CTkEntry(self.inspection_controls, textvariable=variable, placeholder_text=r'\\SERVIDOR\Compartilhamento\Pasta')
            entry.grid(row=i, column=1, sticky='ew', pady=3)
            if i==0:
                entry.configure(state='readonly')
                self.button(self.inspection_controls,'Ver / remover',self.manage_roots).grid(row=i,column=2,padx=(8,0))
            else:
                self.mutable.append(entry)
                self.backup_controls.extend([picker,entry])
        self.backup_switch=ctk.CTkSwitch(self.inspection_controls,text='Criar backup dos HEICs (recomendado)',variable=self.backup_enabled,command=self.update_backup_controls)
        self.backup_switch.grid(row=2,column=0,columnspan=2,sticky='w',pady=(8,3))
        self.mutable.append(self.backup_switch)
        self.clear_batch_button=self.button(self.inspection_controls,'Limpar',self.clear_inspection)
        self.clear_batch_button.grid(row=1,column=2,padx=(8,0),pady=3)
        self.button(self.inspection_controls,'Pré-analisar…',self.preload_dialog).grid(row=2,column=2,padx=(8,0),pady=3)
        use_index=ctk.CTkCheckBox(self.inspection_controls,text='Usar análise salva • atualize para descobrir fotos novas',variable=self.use_index,height=22)
        use_index.grid(row=3,column=0,columnspan=3,sticky='w',pady=(3,0))
        self.mutable.append(use_index)
        self.destination_label = ctk.CTkLabel(self.options, text='Escolha outra pasta para salvar os JPEGs • obrigatório', anchor='w', font=('Segoe UI', 11))
        self.destination_label.grid(row=1, column=0, columnspan=3, sticky='ew', pady=5)
        actions = ctk.CTkFrame(self.options, fg_color='transparent')
        actions.grid(row=2, column=0, columnspan=3, sticky='ew')
        ctk.CTkLabel(actions, text='Qualidade JPEG').pack(side='left', padx=(0, 8))
        self.quality_box = ctk.CTkComboBox(actions, variable=self.quality, values=['50','60','65','70','75','80','85','90','95','100'], width=75)
        self.quality_box.pack(side='left')
        self.mutable.append(self.quality_box)
        self.convert_button = self.button(actions, 'Converter fotos  →', self.start, primary=True)
        self.convert_button.pack(side='right')
        self.stop_button = ctk.CTkButton(actions, text='Parar com segurança', width=150, command=self.request_stop, state='disabled', fg_color='#495574')
        self.stop_button.pack(side='right', padx=8)
        self.drop_area=ctk.CTkFrame(self.options,corner_radius=10,border_width=1,border_color='#7183ca',fg_color=('#eef2ff','#252d4b'))
        self.drop_area.grid(row=3,column=0,columnspan=3,sticky='ew',pady=(10,0))
        self.drop_label=ctk.CTkLabel(self.drop_area,text='Arraste pastas aqui • preparar fila de vistorias',anchor='w',font=('Segoe UI',11))
        self.drop_label.pack(side='left',fill='x',expand=True,padx=10,pady=8)
        self.button(self.drop_area,'Ver fila',self.manage_roots).pack(side='right',padx=6)
        self.button(self.drop_area,'+ Pastas',lambda:self.choose_path(self.root_path)).pack(side='right',padx=6)

        table_frame = ctk.CTkFrame(body, corner_radius=14, fg_color=('#ffffff', '#20253c'))
        table_frame.grid(row=4, column=0, sticky='nsew')
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(table_frame, text='ARQUIVOS  /  Duplo clique para detalhes completos', anchor='w', font=('Segoe UI', 11, 'bold')).grid(row=0, column=0, sticky='ew', padx=12, pady=8)
        columns = [('file','Foto',145),('status','Situação',100),('original_size','HEIC',75),('jpeg_size','JPEG',75),('reduction','Redução',85),('output','JPEG / detalhe',140),('destination','Salvo em',200)]
        self.tree = ttk.Treeview(table_frame, columns=[c[0] for c in columns], show='headings', height=6)
        for key, label, width in columns:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=60, stretch=key in ('file','destination'))
        self.tree.grid(row=1, column=0, sticky='nsew', padx=(8,0))
        scroll = ctk.CTkScrollbar(table_frame, orientation='vertical', command=self.tree.yview, button_color=('#b7c3e0','#485575'), button_hover_color='#7183ca', corner_radius=8)
        scroll.grid(row=1, column=1, sticky='ns')
        horizontal = ctk.CTkScrollbar(table_frame, orientation='horizontal', command=self.tree.xview, button_color=('#b7c3e0','#485575'), button_hover_color='#7183ca', corner_radius=8)
        horizontal.grid(row=2, column=0, sticky='ew', padx=8)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        self.tree.bind('<Double-1>', self.show_details)
        self.progress = ctk.CTkProgressBar(body, height=10, corner_radius=5, progress_color='#5265e8')
        self.progress.grid(row=5, column=0, sticky='ew', pady=(12, 4))
        self.progress.set(0)
        self.status = ctk.CTkLabel(body, text='Pronto para começar.', anchor='w', font=('Segoe UI', 11))
        self.status.grid(row=6, column=0, sticky='ew')
        self.summary_label = ctk.CTkLabel(body, text='', anchor='w', font=('Segoe UI', 11))
        self.summary_label.grid(row=7, column=0, sticky='ew')
        footer = ctk.CTkFrame(body, fg_color='transparent')
        footer.grid(row=8, column=0, sticky='ew', pady=(6,0))
        self.timing_label = ctk.CTkLabel(footer, text='0% • Tempo decorrido: 00:00:00', font=('Segoe UI', 12, 'bold'))
        self.timing_label.pack(side='left')
        ctk.CTkButton(footer, text='Abrir relatório', width=125, command=self.open_report, fg_color='#495574').pack(side='right')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(250, lambda: self.iconbitmap(str(assets/'heiclite.ico')))
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.last_theme = None
        self.refresh()
        self.after(100, self.poll)
        self.folder_drop=None
        from folder_drop import FolderDrop
        try: self.folder_drop=FolderDrop(self,self.receive_folders,target=self.drop_area,elevated=is_admin())
        except OSError as error: self.status.configure(text=f'Use + Pastas / + Fotos para selecionar. {error}')
        self.update_roots()

    def button(self, parent, text, command, primary=False):
        button = ctk.CTkButton(parent, text=text, command=command, height=34, width=110, corner_radius=8,
                               fg_color='#5265e8' if primary else ('#e8edfa', '#2d3554'),
                               text_color='white' if primary else ('#293957', '#e7edff'), hover_color='#7183ca')
        self.mutable.append(button)
        return button

    def set_theme(self, value):
        ctk.set_appearance_mode({'Claro':'light','Escuro':'dark','Automático':'system'}[value])

    def save_view(self):
        self.views[self.mode] = dict(
            rows=[(row, self.tree.item(row)) for row in self.tree.get_children()],
            paths=self.paths, successes=self.successes, sizes=self.converted_sizes, details=self.details,
            cards=[label.cget('text') for label in self.cards], summary=self.summary_label.cget('text'),
            status=self.status.cget('text'), progress=self.progress.get(), progress_text=self.progress_text,
            elapsed=self.elapsed, report=self.last_report)

    def load_view(self):
        view = self.views.get(self.mode, {})
        for row in self.tree.get_children(): self.tree.delete(row)
        self.paths, self.successes = view.get('paths', {}), view.get('successes', {})
        self.converted_sizes, self.details = view.get('sizes', {}), view.get('details', {})
        for row, item in view.get('rows', []):
            self.tree.insert('', 'end', iid=row, values=item['values'], tags=item['tags'])
        for label, text in zip(self.cards, view.get('cards', ['—']*4)): label.configure(text=text)
        self.summary_label.configure(text=view.get('summary', ''))
        self.status.configure(text=view.get('status', 'Pronto para começar.'))
        self.elapsed = view.get('elapsed', 0)
        self.last_report = view.get('report')
        self.set_progress(view.get('progress', 0), view.get('progress_text', '0%'))

    @staticmethod
    def duration(seconds):
        seconds = max(0, int(seconds))
        return f'{seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}'

    def update_timing(self):
        self.timing_label.configure(text=f'{self.progress_text} • Tempo decorrido: {self.duration(self.elapsed)}')

    def set_progress(self, fraction, text=None):
        self.progress.configure(mode='determinate')
        self.progress.set(max(0, min(1, fraction)))
        self.progress_text = text if text is not None else f'{int(min(1, fraction)*100)}%'
        self.update_timing()

    def begin_operation(self, roots):
        self.elapsed = 0
        self.started_at = time.monotonic()
        self.run_data = dict(mode=self.mode, roots=roots, destination=self.destination_path.get() if self.mode=='Fotos' else 'Pasta de cada original',
                             quality=self.quality.get(), status='Iniciada • sem registro de conclusão', folders={}, errors=0,backup_enabled=self.backup_enabled.get() if self.mode=='Vistorias' else None)
        self.history_id = None
        try: self.history_id = self.history.start(self.run_data)
        except Exception as error:
            messagebox.showwarning('Histórico indisponível', f'Não foi possível gravar o histórico local: {error}. Os relatórios das vistorias continuam separados.')

    def record_result(self, source, success, before, after, status=None):
        if self.history_id is None: return
        folder = str(Path(source).parent)
        data = self.run_data['folders'].setdefault(folder, dict(converted=0, errors=0, retained=0, before=0, after=0))
        if success:
            data['converted'] += 1; data['before'] += before; data['after'] += after
        elif status == 'retained': data['retained'] += 1
        else:
            data['errors'] += 1
            self.run_data['errors'] += 1

    def finish_operation(self, status, stats=None):
        if self.started_at is not None: self.elapsed = time.monotonic() - self.started_at
        self.started_at = None
        self.update_timing()
        if self.history_id is None: return
        self.run_data.update(status=status, elapsed=self.elapsed, report=self.last_report, stats=stats)
        try: self.history.finish(self.history_id, self.run_data)
        except Exception as error: messagebox.showwarning('Histórico', f'Não foi possível atualizar o histórico local: {error}')
        self.history_id = None

    def show_history(self):
        dialog = ThemedToplevel(self)
        dialog.title('Histórico de conversões'); dialog.geometry('850x580'); dialog.transient(self)
        ctk.CTkLabel(dialog, text='Histórico de conversões', font=('Segoe UI',22,'bold')).pack(anchor='w',padx=20,pady=(16,4))
        ctk.CTkLabel(dialog, text='Salvo neste computador, na conta atual do Windows. Selecione uma operação para ver as pastas.').pack(anchor='w',padx=20)
        frame = ctk.CTkScrollableFrame(dialog, fg_color='transparent')
        frame.pack(fill='both',expand=True,padx=14,pady=10)
        footer = ctk.CTkFrame(dialog, fg_color='transparent'); footer.pack(fill='x',padx=20,pady=(0,12))
        page = [0]
        def details(entry):
            panel = ThemedToplevel(dialog); panel.title('Pastas e resultados'); panel.geometry('800x500'); panel.transient(dialog)
            box = ctk.CTkTextbox(panel, wrap='word'); box.pack(fill='both',expand=True,padx=15,pady=15)
            lines = [f"{entry['started']} • {entry['mode']} • {entry['status']}",
                     f"Tempo: {self.duration(entry.get('elapsed',0))} • Qualidade: {entry.get('quality','—')}",
                     f"Destino: {entry.get('destination','—')}", '\nOrigens selecionadas:', *entry.get('roots',[]), '\nPastas processadas:']
            for folder, result in entry.get('folders',{}).items():
                lines += [folder, f"  {result['converted']} convertidas • {result['errors']} falhas • {result['retained']} preservadas • {format_size(result['before'])} → {format_size(result['after'])}"]
            if not entry.get('folders'): lines.append('Nenhum resultado registrado nesta operação.')
            if entry.get('backup_enabled') is False: lines.append('\nSEM BACKUP: originais removidos não podem ser restaurados pelo programa.')
            skipped=(entry.get('stats') or {}).get('skipped_roots',[])
            if skipped: lines += ['\nOrigens ignoradas • sem HEIC acessível:', *skipped]
            box.insert('1.0','\n'.join(lines)); box.configure(state='disabled')
            if entry.get('report'):
                def open_saved():
                    try: os.startfile(entry['report'])
                    except OSError as error: messagebox.showerror('Relatório indisponível',str(error),parent=panel)
                ctk.CTkButton(panel,text='Abrir relatório completo',command=open_saved).pack(pady=(0,12))
        def render():
            for child in frame.winfo_children(): child.destroy()
            try: entries = self.history.list(50, page[0]*50)
            except Exception as error:
                ctk.CTkLabel(frame,text=f'Histórico indisponível: {error}',wraplength=700).pack(); return
            if not entries: ctk.CTkLabel(frame,text='Nenhuma operação registrada nesta página.').pack(pady=30)
            for entry in entries:
                total = sum(result['converted'] for result in entry.get('folders',{}).values())
                text = f"{entry['started'].replace('T','  ')} • {entry['mode']} • {entry['status']}\n{total} fotos • {len(entry.get('folders',{}))} pastas • {self.duration(entry.get('elapsed',0))}"
                ctk.CTkButton(frame,text=text,anchor='w',height=66,command=lambda e=entry:details(e),fg_color=('#e8edfa','#2d3554'),text_color=('#293957','#e7edff')).pack(fill='x',pady=4)
            previous.configure(state='normal' if page[0] else 'disabled')
            following.configure(state='normal' if len(entries)==50 else 'disabled')
        def move(delta): page[0]+=delta; render()
        previous = ctk.CTkButton(footer,text='Mais recentes',command=lambda:move(-1)); previous.pack(side='left')
        following = ctk.CTkButton(footer,text='Mais antigas',command=lambda:move(1)); following.pack(side='right')
        render()

    def switch_mode(self, mode):
        if self.busy: return
        if mode == 'Vistorias' and not is_admin():
            self.elevate('--vistorias-admin')
            return
        if mode == self.mode: return
        self.save_view()
        self.mode = mode
        self.load_view()
        inspection = mode == 'Vistorias'
        self.normal.grid_remove() if inspection else self.normal.grid()
        if inspection: self.inspection_controls.grid(row=0, column=0, columnspan=3, sticky='ew')
        else: self.inspection_controls.grid_remove()
        self.drop_area.grid()
        self.update_roots()
        self.heading.configure(text='Vistorias, pasta por pasta.' if inspection else 'Suas fotos, em JPEG.')
        self.subtitle.configure(text='Backup conferido antes de retirar qualquer HEIC da vistoria.' if inspection else 'Converta com rapidez e mantenha os originais.')
        self.convert_button.configure(text='Iniciar vistorias  →' if inspection else 'Converter fotos  →')
        self.update_backup_controls()
        self.refresh()

    def choose_path(self, variable):
        if variable is self.root_path:
            paths=choose_native_folder(self,'Selecione as pastas de vistorias • Ctrl ou Shift',multiple=True)
            if paths:
                try: self.inspection_roots=selection_roots([*self.inspection_roots,*paths])
                except Exception as error: messagebox.showerror('Pastas inválidas',str(error)); return
                self.update_roots()
            return
        value = choose_directory(self, 'Selecionar pasta local ou compartilhada', variable.get())
        if value: variable.set(value)

    def update_roots(self):
        self.root_path.set(str(self.inspection_roots[0]) if len(self.inspection_roots)==1 else f'{len(self.inspection_roots)} pastas na fila • Ver / remover' if self.inspection_roots else '')
        self.drop_label.configure(text='Arraste pastas de vistorias aqui' if self.mode=='Vistorias' else 'Solte fotos HEIC/HEIF ou pastas de vistorias aqui')

    def receive_folders(self,paths):
        if self.busy:
            self.status.configure(text='Aguarde o processamento terminar para adicionar pastas.'); return
        self.stop.clear(); self.phase='selection'; self.set_busy(True)
        self.show_analysis('Preparando seleção')
        def classify():
            folders=[]; photos=[]; error=None
            try:
                for value in paths:
                    if self.stop.is_set(): break
                    path=Path(value)
                    if not path.is_absolute(): continue
                    if path.is_dir(): folders.append(path)
                    elif path.suffix.lower() in EXTENSIONS and path.is_file(): photos.append(path)
            except Exception as exception: error=str(exception)
            self.events.put(('selection_done',folders,photos,error,self.stop.is_set()))
        threading.Thread(target=classify,daemon=True).start()

    def apply_selection(self,folders,photos):
        try:
            added=0
            if photos and self.mode=='Fotos':
                previous=len(self.paths); self.add_paths(photos); added=len(self.paths)-previous
            if folders: self.inspection_roots=selection_roots([*self.inspection_roots,*folders])
            self.update_roots()
            messages=[]
            if photos and self.mode=='Fotos': messages.append(f'{added} foto(s) adicionada(s). Escolha o destino e clique em Converter fotos.')
            elif photos: messages.append('Para fotos soltas, use Converter fotos. Neste módulo, arraste pastas.')
            if folders: messages.append(f'{len(self.inspection_roots)} pastas na fila de vistorias. Confira em Ver fila antes de iniciar.')
            self.status.configure(text=' '.join(messages) or 'Arraste pastas ou fotos HEIC/HEIF. Outros formatos não são adicionados.')
        except Exception as error: messagebox.showerror('Pastas inválidas',str(error))

    def show_analysis(self,title='Analisando pastas'):
        if self.analysis_dialog is not None: return
        dialog=ThemedToplevel(self); self.analysis_dialog=dialog
        dialog.title(title); dialog.geometry('600x280'); dialog.transient(self)
        ctk.CTkLabel(dialog,text=title,font=('Segoe UI',21,'bold')).pack(anchor='w',padx=20,pady=(18,8))
        self.analysis_counts=ctk.CTkLabel(dialog,text='Validando caminhos…',anchor='w')
        self.analysis_counts.pack(fill='x',padx=20)
        self.analysis_path=ctk.CTkLabel(dialog,text='A janela permanece disponível durante a leitura.',wraplength=550,anchor='w',justify='left',height=65)
        self.analysis_path.pack(fill='x',padx=20,pady=6)
        self.analysis_bar=ctk.CTkProgressBar(dialog,mode='indeterminate'); self.analysis_bar.pack(fill='x',padx=20,pady=10); self.analysis_bar.start()
        self.analysis_cancel=ctk.CTkButton(dialog,text='Cancelar análise',command=self.request_stop)
        self.analysis_cancel.pack(pady=10)
        dialog.protocol('WM_DELETE_WINDOW',self.request_stop)

    def close_analysis(self):
        if self.analysis_dialog is not None:
            self.analysis_bar.stop(); self.analysis_dialog.destroy(); self.analysis_dialog=None

    def preload_dialog(self):
        dialog=ThemedToplevel(self); dialog.title('Pré-carregamento de vistorias'); dialog.geometry('660x300'); dialog.transient(self)
        ctk.CTkLabel(dialog,text='Analisar agora, converter depois',font=('Segoe UI',21,'bold')).pack(anchor='w',padx=20,pady=(18,8))
        ctk.CTkLabel(dialog,text='Cole a raiz do servidor ou analise a fila selecionada.\nAtualiza o índice sem converter, copiar ou apagar fotos.',justify='left').pack(anchor='w',padx=20)
        path=tk.StringVar(value=str(self.inspection_roots[0]) if len(self.inspection_roots)==1 else '')
        entry=ctk.CTkEntry(dialog,textvariable=path,placeholder_text=r'\\servidor\vistorias'); entry.pack(fill='x',padx=20,pady=14)
        def choose():
            value=choose_directory(dialog,'Selecione a raiz para pré-análise')
            if value: path.set(value)
        ctk.CTkButton(dialog,text='Escolher pasta…',command=choose).pack(anchor='w',padx=20)
        def begin(paths):
            if self.busy: return
            try: roots=selection_roots(paths)
            except Exception as error: messagebox.showerror('Caminho inválido',str(error),parent=dialog); return
            if not roots: return
            dialog.destroy()
            self.inspection_roots=roots; self.update_roots()
            self.stop.clear(); self.phase='preload'; self.set_busy(True)
            self.show_analysis('Pré-análise • somente leitura')
            threading.Thread(target=preload_roots,args=(roots,self.events,self.stop),daemon=True).start()
        buttons=ctk.CTkFrame(dialog,fg_color='transparent'); buttons.pack(fill='x',padx=20,pady=16)
        ctk.CTkButton(buttons,text='Analisar caminho',command=lambda:begin([path.get().strip()])).pack(side='left')
        ctk.CTkButton(buttons,text=f'Analisar fila ({len(self.inspection_roots)})',command=lambda:begin(list(self.inspection_roots)),state='normal' if self.inspection_roots else 'disabled').pack(side='right')

    def manage_roots(self):
        dialog=ThemedToplevel(self)
        dialog.title('Pastas de vistorias selecionadas')
        dialog.geometry('760x350'); dialog.transient(self)
        ctk.CTkLabel(dialog,text='Cada pasta inclui suas subpastas. A fila é processada em sequência.').pack(pady=12)
        dark=ctk.get_appearance_mode()=='Dark'
        listing=tk.Listbox(dialog,selectmode='extended',font=('Segoe UI',11),bg='#20253c' if dark else 'white',fg='#e7edff' if dark else '#293957',selectbackground='#5265e8',borderwidth=0,highlightthickness=0)
        listing.pack(fill='both',expand=True,padx=15)
        scroll=ctk.CTkScrollbar(dialog,orientation='horizontal',command=listing.xview)
        scroll.pack(fill='x',padx=15); listing.configure(xscrollcommand=scroll.set)
        for root in self.inspection_roots: listing.insert('end',str(root))
        def remove():
            for index in reversed(listing.curselection()):
                del self.inspection_roots[index]; listing.delete(index)
            self.update_roots()
        buttons=ctk.CTkFrame(dialog,fg_color='transparent'); buttons.pack(fill='x',padx=15,pady=12)
        ctk.CTkButton(buttons,text='Remover selecionadas',command=remove).pack(side='left')
        ctk.CTkButton(buttons,text='Concluir',command=dialog.destroy).pack(side='right')
        dialog.wait_visibility(); dialog.grab_set()

    def choose_files(self):
        self.add_paths(filedialog.askopenfilenames(filetypes=[('Fotos HEIC / HEIF','*.heic *.heif *.HEIC *.HEIF')]))

    def choose_folder(self):
        value = choose_directory(self)
        if value:
            try: self.add_paths(Path(value).iterdir())
            except OSError as error: messagebox.showerror('Pasta indisponível', str(error))

    def choose_destination(self):
        value = choose_directory(self, title='Escolha uma pasta diferente da origem para os JPEGs', initial=self.destination_path.get())
        if value: self.destination_path.set(value)
        self.destination_mode.set('other')
        self.update_destination()

    def update_destination(self):
        text = 'JPEGs na pasta de cada original • HEICs retirados após backup e validação' if self.mode == 'Vistorias' else 'Destino: '+(self.destination_path.get() or 'escolha outra pasta para salvar • obrigatório')
        if self.mode=='Vistorias' and not self.backup_enabled.get():
            text='SEM BACKUP • HEIC removido após validar o JPEG • sem restauração do original'
        self.destination_label.configure(text=text)
        self.destination_label.configure(text_color=('#a33122','#ffad91') if self.mode=='Vistorias' and not self.backup_enabled.get() else ('#293957','#e7edff'))
        if self.mode == 'Fotos':
            for row in self.paths:
                if row not in self.successes: self.tree.set(row, 'destination', self.destination_path.get() or 'Escolha o destino')
        self.refresh()

    def update_backup_controls(self):
        for widget in self.backup_controls:
            widget.configure(state='normal' if self.backup_enabled.get() and not self.busy else 'disabled')
        self.update_destination()
        if self.mode=='Vistorias' and not self.busy:
            self.subtitle.configure(text='Backup conferido antes de retirar qualquer HEIC da vistoria.' if self.backup_enabled.get() else 'Sem backup: o JPEG será conferido antes da remoção definitiva do HEIC.')

    def add_paths(self, paths):
        known = set(self.paths.values())
        for path in paths:
            path = Path(path).resolve()
            if path.suffix.lower() not in EXTENSIONS or path in known or not path.is_file(): continue
            row = self.tree.insert('', 'end', values=(path.name,'Aguardando',format_size(path.stat().st_size),'—','—','—',self.destination_path.get() or 'Escolha o destino'))
            self.paths[row] = path
            known.add(path)
        self.refresh()

    def clear_inspection(self):
        if self.busy: return
        self.inspection_roots.clear()
        self.update_roots()
        self.clear()

    def clear(self):
        if self.busy: return
        for row in self.tree.get_children(): self.tree.delete(row)
        self.paths.clear(); self.successes.clear(); self.converted_sizes.clear(); self.details.clear()
        self.elapsed = 0; self.last_report = None
        self.set_progress(0)
        self.status.configure(text='Pronto para começar.')
        self.update_summary()
        self.refresh()

    def refresh(self):
        self.convert_button.configure(state='normal' if not self.busy and (self.mode=='Vistorias' or (bool(self.destination_path.get()) and any(r not in self.successes for r in self.paths))) else 'disabled')


    def update_summary(self, stats=None):
        before = stats['before'] if stats else sum(v[0] for v in self.converted_sizes.values())
        after = stats['after'] if stats else sum(v[1] for v in self.converted_sizes.values())
        count = stats['converted'] if stats else len(self.converted_sizes)
        for label, value in zip(self.cards, [str(count), format_size(before), format_size(after), format_reduction(before,after)]): label.configure(text=value)
        summary = f'{count} fotos • HEIC {format_size(before)} → JPEG {format_size(after)} • {format_reduction(before,after)}' if stats else format_summary(self.converted_sizes.values())
        failures = sum(self.tree.set(row,'status') == 'Falha' for row in self.paths)
        if failures and not stats: summary += f'\n{failures} falha(s), fora dos totais.'
        self.summary_label.configure(text=summary)

    def set_busy(self, busy):
        self.busy = busy
        for widget in self.mutable: widget.configure(state='disabled' if busy else 'normal')
        self.stop_button.configure(state='normal' if busy and self.mode=='Vistorias' else 'disabled')
        self.refresh()
        self.update_backup_controls()

    def start(self):
        if self.mode == 'Vistorias' and not is_admin():
            self.elevate('--vistorias-admin'); return
        try:
            quality = int(self.quality.get())
            if not 1 <= quality <= 100: raise ValueError()
        except ValueError:
            messagebox.showerror('Qualidade', 'Informe um número de 1 a 100.'); return
        if self.mode == 'Vistorias':
            if not self.inspection_roots or (self.backup_enabled.get() and not self.backup_path.get()):
                messagebox.showinfo('Escolha as pastas', 'Selecione a raiz das vistorias e uma pasta externa para o backup.'); return
            backup_enabled=self.backup_enabled.get()
            try:
                roots=selection_roots(self.inspection_roots)
                backup=Path(self.backup_path.get()) if backup_enabled else report_directory()
            except Exception as error:
                messagebox.showerror('Pastas inválidas', str(error)); return
            self.inspection_roots=roots; self.update_roots()
            if backup_enabled: self.backup_path.set(str(backup))
            preview='\n'.join(str(root) for root in roots[:8])
            if len(roots)>8: preview+=f'\n… e mais {len(roots)-8}. Confira a lista completa em Ver / remover.'
            protection=f'Backup integral: {backup}\nHEIC retirado somente após backup e validação.' if backup_enabled else 'SEM BACKUP DOS ORIGINAIS.\nApós validar o JPEG, o HEIC será removido definitivamente. Não será possível restaurá-lo pelo programa. JPEG usa compressão com perda e não preserva todos os dados do HEIC.'
            if not messagebox.askyesno('Converter vistorias' if backup_enabled else 'Converter e remover HEICs SEM BACKUP', f'{len(roots)} pasta(s), incluindo subpastas:\n{preview}\n\n{protection}\n\nJPEG qualidade {quality} na mesma pasta.\n\nIniciar a fila?',default='no'): return
            self.clear(); self.stop.clear(); self.last_report = None
            self.begin_operation([str(root) for root in roots])
            self.set_busy(True)
            self.phase='analysis'; self.show_analysis()
            self.set_progress(0, 'Analisando pastas…')
            threading.Thread(target=run_inspection_queue, args=(roots, str(backup), self.events, self.stop, quality, self.max_workers,backup_enabled,self.use_index.get()), daemon=True).start()
        else:
            if not self.destination_path.get() or not Path(self.destination_path.get()).is_dir():
                messagebox.showerror('Destino', 'Selecione uma pasta de destino disponível.'); return
            if self.destination_mode.get() == 'other' and not self.destination_path.get():
                messagebox.showerror('Destino', 'Selecione uma pasta de destino.'); return
            work = [(r,p) for r,p in self.paths.items() if r not in self.successes]
            if not work: return
            destination = Path(self.destination_path.get()).resolve()
            try: same_origin = any(destination.samefile(path.parent) for _, path in work)
            except OSError as error:
                messagebox.showerror('Pasta indisponível', str(error)); return
            if same_origin:
                messagebox.showerror('Destino', 'Escolha uma pasta diferente da pasta original das fotos.'); return
            self.begin_operation(sorted({str(path.parent) for _, path in work}))
            self.completed, self.total = 0, len(work)
            self.set_progress(0)
            self.set_busy(True)
            output = Path(self.destination_path.get()) if self.destination_path.get() else None
            threading.Thread(target=self.worker, args=(work,quality,output), daemon=True).start()

    def worker(self, work, quality, output_folder=None):
        run_batch(work, quality, self.events, self.accelerated, self.max_workers, output_folder)

    def request_stop(self):
        self.stop.set()
        self.stop_button.configure(state='disabled')
        self.status.configure(text='Parando após concluir as fotos já em andamento…')
        if self.analysis_dialog is not None:
            self.analysis_cancel.configure(state='disabled',text='Cancelamento solicitado')
            self.analysis_counts.configure(text='Aguardando a leitura atual do Windows terminar…')

    def poll(self):
        theme = ctk.get_appearance_mode()
        if theme != self.last_theme:
            dark = theme == 'Dark'
            bg, fg = ('#20253c','#e7edff') if dark else ('#ffffff','#293957')
            self.style.configure('Treeview', background=bg, fieldbackground=bg, foreground=fg, rowheight=29, borderwidth=0, font=('Segoe UI',10))
            self.style.configure('Treeview.Heading', background='#2d3554' if dark else '#e8edfa', foreground=fg, font=('Segoe UI',10,'bold'), relief='flat')
            self.style.map('Treeview', background=[('selected','#5265e8')], foreground=[('selected','white')])
            self.tree.tag_configure('error', foreground='#ff8b99' if dark else '#b42645')
            self.tree.tag_configure('ok', foreground='#75dfce' if dark else '#147362')
            self.last_theme = theme
            self.after(300, lambda: apply_titlebar(self, ctk.get_appearance_mode() == 'Dark'))
        if self.started_at is not None:
            self.elapsed = time.monotonic() - self.started_at
            self.update_timing()
        for _ in range(100):
            try: event = self.events.get_nowait()
            except queue.Empty: break
            kind = event[0]
            if kind=='selection_done':
                self.close_analysis(); self.phase=None; self.set_busy(False)
                if event[4]: self.status.configure(text='Seleção cancelada. A fila anterior foi mantida.')
                elif event[3]: messagebox.showerror('Seleção',event[3])
                else: self.apply_selection(event[1],event[2])
            elif kind=='analysis_progress':
                if self.analysis_dialog is not None:
                    self.analysis_counts.configure(text=f'{event[2]} pastas lidas • {event[3]} HEIC/HEIF • {event[4]} pastas sem HEIC • {event[5]} falhas')
                    self.analysis_path.configure(text=event[1])
            elif kind=='analysis_root':
                if self.analysis_dialog is not None: self.analysis_path.configure(text=f'Origem {event[1]}/{event[2]}: {event[3]}')
            elif kind=='analysis_cached':
                self.status.configure(text=f'Usando análise de {event[2]} • {event[3]} fotos • {event[1]}')
            elif kind=='analysis_notice': self.status.configure(text=event[1])
            elif kind=='analysis_finished':
                self.close_analysis(); self.phase='conversion'
            elif kind=='preload_done':
                self.close_analysis(); self.phase=None; self.set_busy(False)
                results,cancelled,error=event[1:]
                self.status.configure(text=f'{"Pré-análise cancelada" if cancelled else "Pré-análise finalizada"} • {sum(r["photos"] for r in results)} HEIC/HEIF • {sum(r["empty"] for r in results)} pastas sem HEIC • {sum(r["errors"] for r in results)} falhas')
                if error: messagebox.showerror('Pré-análise',error)
                elif results: messagebox.showinfo('Pré-análise', 'Índice salvo. A conversão poderá usar esta análise, inclusive para subpastas selecionadas depois.\n\nAtualize a análise para descobrir fotos adicionadas depois. Origens com falhas de leitura precisarão ser analisadas novamente.')
            elif kind == 'working': self.tree.set(event[1], 'status', 'Convertendo')
            elif kind in ('ok','error'):
                row = event[1]
                if kind == 'ok':
                    self.successes[row] = (event[2],event[3])
                    self.converted_sizes[row] = (event[3][0], event[4])
                    for key,value in [('status','Convertida'),('jpeg_size',format_size(event[4])),('reduction',format_reduction(event[3][0],event[4])),('output',event[2].name),('destination',str(event[2].parent))]: self.tree.set(row,key,value)
                else:
                    self.tree.set(row,'status','Falha'); self.tree.set(row,'output',str(event[2]))
                self.tree.item(row,tags=(kind,))
                self.completed = getattr(self,'completed',0)+1
                self.set_progress(self.completed/max(1,getattr(self,'total',len(self.paths))))
                self.record_result(self.paths[row], kind == 'ok', event[3][0] if kind == 'ok' else 0, event[4] if kind == 'ok' else 0)
                self.update_summary()
            elif kind == 'done':
                self.finish_operation('Concluído com falhas' if self.run_data.get('errors') else 'Concluído')
                self.set_busy(False)
                self.status.configure(text=f'{len(self.successes)} convertidas • {len(self.paths)-len(self.successes)} pendentes ou com falha.')
            elif kind == 'inspection_result':
                result,stats = event[1:]
                source = Path(result['source']); jpeg = Path(result['jpeg']) if result.get('jpeg') else None
                row = self.tree.insert('', 'end', values=(source.name, {'ok':'Conferida','error':'Falha','retained':'Preservada'}[result['status']],format_size(result.get('before',0)),format_size(result.get('after',0)),format_reduction(result.get('before',0),result.get('after',0)),jpeg.name if jpeg else result['detail'],str(jpeg.parent) if jpeg else 'Original mantido'),tags=(result['status'],))
                self.details[row] = result
                self.record_result(source, result['status'] == 'ok', result.get('before',0), result.get('after',0), result['status'])
                children = self.tree.get_children()
                if len(children)>1000:
                    old=children[0]; self.tree.delete(old); self.details.pop(old,None)
                self.tree.see(row)
                self.update_summary(stats)
            elif kind == 'inspection_counting':
                self.set_progress(0, 'Contando fotos…')
                self.status.configure(text='Contando fotos nas pastas selecionadas…')
            elif kind == 'inspection_skipped':
                self.status.configure(text=('Origem sem HEIC acessível; confira as ocorrências: ' if event[2] else 'Ignorada • sem HEIC: ')+event[1])
            elif kind == 'inspection_progress':
                done, total = event[1:]
                self.set_progress(min(.99, done/max(1,total)), f'{min(99, int(100*done/max(1,total)))}% • {done}/{total} fotos processadas')
            elif kind=='inspection_root':
                self.subtitle.configure(text=f'Origem {event[1]} de {event[2]}: {event[3]}')
            elif kind in ('inspection_scan','inspection_folder'):
                self.status.configure(text='Pasta atual: '+event[1])
            elif kind == 'inspection_fatal': messagebox.showerror('Processo interrompido',event[1])
            elif kind == 'inspection_done':
                self.close_analysis(); self.phase=None
                stats = event[1]; self.last_report = stats.get('report')
                if not stats['cancelled'] and not stats.get('failed'): self.set_progress(1)
                self.finish_operation('Interrompido' if stats['cancelled'] or stats.get('failed') else 'Concluído com ocorrências' if stats['errors'] or stats['retained'] else 'Concluído', stats)
                self.set_busy(False); self.update_summary(stats)
                self.status.configure(text=f'{"Interrompido" if stats["cancelled"] or stats.get("failed") else "Concluído"} • {stats.get("completed_roots",1)}/{stats.get("total_roots",1)} origens • {stats["visited"]} pastas • {stats["converted"]} JPEGs • {stats["errors"]} falhas')
                skipped=len(stats.get('skipped_roots',[]))
                if skipped:
                    self.status.configure(text=f'{"Interrompido" if stats["cancelled"] or stats.get("failed") else "Verificação concluída"} • {stats.get("completed_roots",0)} origens processadas • {skipped} sem HEIC acessível • {stats["converted"]} JPEGs • {stats["errors"]} falhas')
                self.subtitle.configure(text='Últimos 1.000 resultados na lista. Consulte o relatório completo.')
            elif kind == 'restore_done':
                self.finish_operation('Restauração')
                self.set_busy(False); self.status.configure(text=event[1])
                messagebox.showinfo('Restauração',event[1])
        self.after(100,self.poll)

    def show_details(self, _event=None):
        rows = self.tree.selection()
        if not rows: return
        row = rows[0]
        if row in self.details:
            result = self.details[row]
            text = '\n\n'.join(f'{label}: {result.get(key,"—")}' for label,key in [('Original','source'),('JPEG','jpeg'),('Backup','backup'),('Detalhe','detail')])
        else: text = f'Original: {self.paths[row]}\n\nDestino: {self.tree.set(row,"destination")}\n\nJPEG / detalhe: {self.tree.set(row,"output")}'
        messagebox.showinfo('Detalhes da foto',text)

    def open_report(self):
        if self.last_report:
            try: os.startfile(self.last_report)
            except OSError as error: messagebox.showerror('Relatório indisponível',str(error))
        else: messagebox.showinfo('Relatório','O relatório fica disponível após executar ou interromper uma vistoria.')

    def restore(self):
        if not is_admin():
            self.elevate('--restaurar-admin'); return
        folder=choose_directory(self,title='Selecione a pasta HEICLite que contém manifesto.sqlite3')
        if not folder: return
        if not (Path(folder)/'manifesto.sqlite3').is_file():
            messagebox.showerror('Backup','Esta pasta não contém o diário do HEICLite.'); return
        if not messagebox.askyesno('Restaurar HEICs','Copiar os HEICs de volta às pastas originais? Arquivos existentes e JPEGs serão mantidos.'): return
        self.elapsed = 0; self.started_at = time.monotonic()
        self.set_progress(0, 'Restaurando…')
        self.set_busy(True); self.stop_button.configure(state='disabled')
        self.status.configure(text='Restaurando cópias verificadas…')
        def work():
            try:
                restored,skipped=restore_originals(folder)
                text=f'{restored} originais restaurados; {skipped} já existentes preservados.'
            except Exception as error: text=f'Restauração interrompida: {error}'
            self.events.put(('restore_done',text))
        threading.Thread(target=work,daemon=True).start()

    def elevate(self, action):
        try:
            if action=='--vistorias-admin' and self.inspection_roots:
                launch_admin(action,folders=self.inspection_roots,backup=self.backup_path.get(),quality=self.quality.get())
            else: launch_admin(action)
            self.status.configure(text='Janela administrativa solicitada ao Windows. A conversão comum continua disponível aqui.')
        except Exception as error:
            messagebox.showinfo('Autorização necessária',str(error))

    def close(self):
        if self.busy: messagebox.showinfo('Processamento em andamento','Use Parar com segurança e aguarde as fotos atuais terminarem antes de fechar.')
        else: self.destroy()

    def destroy(self):
        self.close_analysis()
        drop=getattr(self,'folder_drop',None)
        if drop: drop.close()
        super().destroy()
