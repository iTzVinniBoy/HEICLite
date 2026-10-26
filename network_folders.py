"""Navegação explícita de compartilhamentos SMB, sem depender de drives mapeados."""
import ctypes
import ntpath
import os
import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
from window_theme import ThemedToplevel


def normalize_location(value):
    value = value.strip().strip('"').replace('/', '\\')
    if not value:
        raise ValueError('Informe uma pasta ou um servidor, como \\\\SERVIDOR.')
    if value.startswith(('\\\\?\\', '\\\\.\\')):
        raise ValueError('Use o caminho normal da pasta, como \\\\SERVIDOR\\Compartilhamento.')
    if not value.startswith('\\\\') and not ntpath.isabs(value):
        value = '\\\\' + value.strip('\\')
    return ntpath.normpath(value)


def server_only(value):
    return value.startswith('\\\\') and len(value.strip('\\').split('\\')) == 1


def list_shares(server):
    from ctypes import wintypes
    class Share(ctypes.Structure):
        _fields_ = [('name', wintypes.LPWSTR), ('type', wintypes.DWORD), ('remark', wintypes.LPWSTR)]
    api = ctypes.WinDLL('Netapi32.dll')
    enum = api.NetShareEnum
    enum.argtypes = [wintypes.LPWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
                     wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
    enum.restype = wintypes.DWORD
    api.NetApiBufferFree.argtypes = [ctypes.c_void_p]
    api.NetApiBufferFree.restype = wintypes.DWORD
    resume = wintypes.DWORD(0)
    results = []
    while True:
        buffer = ctypes.c_void_p()
        count, total = wintypes.DWORD(), wintypes.DWORD()
        previous = resume.value
        try:
            status = enum(server, 1, ctypes.byref(buffer), 65536, ctypes.byref(count), ctypes.byref(total), ctypes.byref(resume))
            if status not in (0, 234): raise ctypes.WinError(status)
            shares = ctypes.cast(buffer, ctypes.POINTER(Share))
            for i in range(count.value):
                if shares[i].type & 0xff == 0:
                    results.append(ntpath.join(server, shares[i].name))
        finally:
            if buffer: api.NetApiBufferFree(buffer)
        if status == 0: break
        if resume.value == previous: raise OSError('O servidor não avançou na listagem. Informe o caminho completo do compartilhamento.')
    return sorted(set(results), key=str.casefold)


def list_folders(location):
    if server_only(location): return list_shares(location)
    with os.scandir(location) as entries:
        return sorted((entry.path for entry in entries if entry.is_dir()), key=str.casefold)


class FolderPicker(ThemedToplevel):
    def __init__(self, parent, title, initial=''):
        super().__init__(parent)
        self.title(title)
        self.geometry('760x520')
        self.minsize(600, 400)
        self.transient(parent)
        self.result = ''
        self.current = ''
        self.children_paths = []
        self.events = queue.Queue()
        self.request_id = 0
        self.location = tk.StringVar(value=initial)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(self, text='Pasta local ou servidor de rede', font=('Segoe UI',20,'bold')).grid(row=0,column=0,sticky='w',padx=20,pady=(15,5))
        ctk.CTkLabel(self,text=r'Digite \\SERVIDOR para listar compartilhamentos ou cole \\SERVIDOR\Pasta.',anchor='w').grid(row=1,column=0,sticky='ew',padx=20)
        bar=ctk.CTkFrame(self,fg_color='transparent')
        bar.grid(row=2,column=0,sticky='ew',padx=20,pady=10)
        bar.grid_columnconfigure(0,weight=1)
        entry=ctk.CTkEntry(bar,textvariable=self.location)
        entry.grid(row=0,column=0,sticky='ew',padx=(0,8))
        entry.bind('<Return>',lambda _:self.navigate())
        ctk.CTkButton(bar,text='Abrir / listar',width=110,command=self.navigate).grid(row=0,column=1)
        ctk.CTkButton(bar,text='↑',width=35,command=self.up).grid(row=0,column=2,padx=(8,0))
        frame=ctk.CTkFrame(self)
        frame.grid(row=3,column=0,sticky='nsew',padx=20)
        frame.grid_columnconfigure(0,weight=1); frame.grid_rowconfigure(0,weight=1)
        dark=ctk.get_appearance_mode()=='Dark'
        self.listbox=tk.Listbox(frame,bg='#20253c' if dark else 'white',fg='#e7edff' if dark else '#293957',selectbackground='#5265e8',font=('Segoe UI',11),borderwidth=0,highlightthickness=0,activestyle='none')
        self.listbox.grid(row=0,column=0,sticky='nsew',padx=6,pady=6)
        scroll=ctk.CTkScrollbar(frame,command=self.listbox.yview)
        scroll.grid(row=0,column=1,sticky='ns'); self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.bind('<Double-1>',self.enter_selected)
        self.listbox.bind('<Return>',self.enter_selected)
        self.info=ctk.CTkLabel(self,text='A conta usada nesta janela precisa ter acesso ao servidor.',wraplength=700,anchor='w',justify='left')
        self.info.grid(row=4,column=0,sticky='ew',padx=20,pady=8)
        footer=ctk.CTkFrame(self,fg_color='transparent')
        footer.grid(row=5,column=0,sticky='ew',padx=20,pady=(0,15))
        ctk.CTkButton(footer,text='Procurar no Windows',command=self.native).pack(side='left')
        self.choose=ctk.CTkButton(footer,text='Usar esta pasta',command=self.accept,state='disabled')
        self.choose.pack(side='right')
        ctk.CTkButton(footer,text='Cancelar',width=85,command=self.destroy).pack(side='right',padx=8)
        self.timer=self.after(100,self.poll)
        self.protocol('WM_DELETE_WINDOW',self.destroy)
        self.wait_visibility(); self.grab_set(); entry.focus_set()
        if initial: self.navigate()

    def navigate(self):
        try: location=normalize_location(self.location.get())
        except ValueError as error: self.info.configure(text=str(error)); return
        self.location.set(location)
        self.request_id+=1
        request=self.request_id
        self.current=''; self.children_paths=[]; self.listbox.delete(0,'end')
        self.choose.configure(state='disabled'); self.info.configure(text='Consultando pastas… Você pode cancelar ou informar outro caminho.')
        events=self.events
        def work():
            try: events.put((request,location,list_folders(location),None))
            except Exception as error: events.put((request,location,[],str(error)))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        try:
            while True:
                request,location,children,error=self.events.get_nowait()
                if request!=self.request_id: continue
                if error:
                    self.info.configure(text=f'Não foi possível acessar: {error}\nConfira o servidor e as permissões da conta administrativa. Se a listagem for restrita, cole o caminho completo do compartilhamento.')
                    continue
                self.current=location; self.children_paths=children
                for child in children: self.listbox.insert('end',child.rstrip('\\').rsplit('\\',1)[-1])
                self.choose.configure(state='disabled' if server_only(location) else 'normal')
                self.info.configure(text=f'{len(children)} pastas encontradas. Duplo clique para entrar.' if children else 'Nenhuma subpasta. Você pode selecionar esta pasta.' if not server_only(location) else 'Nenhum compartilhamento listado. Informe o caminho completo, se você o conhece.')
        except queue.Empty: pass
        self.timer=self.after(100,self.poll)

    def enter_selected(self,_event=None):
        selected=self.listbox.curselection()
        if selected:
            self.location.set(self.children_paths[selected[0]]); self.navigate()

    def up(self):
        try: location=normalize_location(self.location.get())
        except ValueError: return
        if server_only(location): return
        if ntpath.dirname(location)==location: return
        parts=location.strip('\\').split('\\')
        parent='\\\\'+parts[0] if location.startswith('\\\\') and len(parts)==2 else ntpath.dirname(location.rstrip('\\'))
        self.location.set(parent); self.navigate()

    def native(self):
        value=filedialog.askdirectory(parent=self,title='Selecionar pasta',mustexist=True)
        if value: self.location.set(value); self.navigate()

    def accept(self):
        if self.current and not server_only(self.current):
            # Se o texto foi editado, consulte o novo endereço antes de aceitar.
            try: same=normalize_location(self.location.get())==self.current
            except ValueError: same=False
            if not same: self.navigate(); return
            self.result=self.current; self.destroy()

    def destroy(self):
        if hasattr(self,'timer'): self.after_cancel(self.timer)
        super().destroy()


def choose_directory(parent,title='Selecionar pasta',initial=''):
    from windows_folders import choose_native_folder
    return choose_native_folder(parent,title,initial)
