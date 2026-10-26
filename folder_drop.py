"""Recebe caminhos do Explorer; o drop apenas prepara a seleção, nunca executa ações."""
import ctypes
import queue
from ctypes import wintypes


class FolderDrop:
    def __init__(self,root,callback,target=None,elevated=False):
        self.root=root
        self.target=target if target is not None else root
        self.handles=set()
        self.closed=False
        self.pending=None
        self.deliveries=queue.SimpleQueue()
        self.callback=callback
        self.delivery_timer=None
        self.elevated=elevated
        self.shell=ctypes.WinDLL('shell32')
        self.common=ctypes.WinDLL('comctl32')
        user=ctypes.WinDLL('user32')
        self.user=user
        user.ChangeWindowMessageFilterEx.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.DWORD,ctypes.c_void_p]
        user.ChangeWindowMessageFilterEx.restype=wintypes.BOOL
        user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]; user.GetAncestor.restype=wintypes.HWND
        root.update_idletasks()
        self.hwnd=user.GetAncestor(root.winfo_id(),2)
        self.identifier=id(self)
        signature=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM,ctypes.c_size_t,ctypes.c_size_t)
        self.common.SetWindowSubclass.argtypes=[wintypes.HWND,signature,ctypes.c_size_t,ctypes.c_size_t]
        self.common.SetWindowSubclass.restype=wintypes.BOOL
        self.common.RemoveWindowSubclass.argtypes=[wintypes.HWND,signature,ctypes.c_size_t]
        self.common.DefSubclassProc.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        self.common.DefSubclassProc.restype=ctypes.c_ssize_t
        self.shell.DragAcceptFiles.argtypes=[wintypes.HWND,wintypes.BOOL]
        self.shell.DragQueryFileW.argtypes=[wintypes.HANDLE,wintypes.UINT,wintypes.LPWSTR,wintypes.UINT]
        self.shell.DragQueryFileW.restype=wintypes.UINT
        self.shell.DragFinish.argtypes=[wintypes.HANDLE]
        @signature
        def receive(hwnd,message,wparam,lparam,identifier,data):
            if message==0x233:
                paths=[]
                try:
                    count=self.shell.DragQueryFileW(wparam,0xffffffff,None,0)
                    if count>10000: return 0
                    for index in range(count):
                        size=self.shell.DragQueryFileW(wparam,index,None,0)+1
                        if size>32768: continue
                        name=ctypes.create_unicode_buffer(size)
                        self.shell.DragQueryFileW(wparam,index,name,size)
                        paths.append(name.value)
                finally: self.shell.DragFinish(wparam)
                # Nunca chama Tcl/Tk de dentro de um callback nativo. O evento
                # pode chegar enquanto mainloop está com o estado Python suspenso.
                self.deliveries.put(paths)
                return 0
            if message==0x82:  # WM_NCDESTROY: nunca deixa callbacks em HWNDs destruídos.
                self.handles.discard(hwnd)
                self.common.RemoveWindowSubclass(hwnd,self.handler,self.identifier)
            return self.common.DefSubclassProc(hwnd,message,wparam,lparam)
        self.handler=receive
        self.refresh()
        self.map_binding=self.root.bind('<Map>',self.schedule_refresh,add='+')
        self.delivery_timer=self.root.after(50,self.deliver)

    def deliver(self):
        self.delivery_timer=None
        if self.closed: return
        try:
            for _ in range(20):
                try: paths=self.deliveries.get_nowait()
                except queue.Empty: break
                self.callback(paths)
        finally:
            if not self.closed: self.delivery_timer=self.root.after(50,self.deliver)

    def schedule_refresh(self,event=None):
        if self.closed or self.pending is not None: return
        self.pending=self.root.after_idle(self.refresh)

    def refresh(self):
        self.pending=None
        if self.closed: return
        # Frames, canvases e rótulos Tk têm HWNDs próprios. O Explorer pode
        # entregar o drop diretamente ao componente sob o ponteiro.
        widgets=[self.target]
        handles={self.hwnd}
        while widgets:
            widget=widgets.pop()
            handles.add(widget.winfo_id())
            widgets.extend(widget.winfo_children())
        for hwnd in handles:
            if hwnd not in self.handles:
                if not self.common.SetWindowSubclass(hwnd,self.handler,self.identifier,0):
                    self.close()
                    raise OSError('Não foi possível ativar arrastar e soltar.')
                self.handles.add(hwnd)
                if self.elevated:
                    # Exceção restrita aos HWNDs receptores e às mensagens de
                    # transferência de arquivos. Não habilita comandos nem UAC.
                    for message in (0x233,0x49):
                        if not self.user.ChangeWindowMessageFilterEx(hwnd,message,1,None):
                            self.close()
                            raise OSError('Windows não permitiu receber arquivos nesta janela. Use + Pastas / + Fotos.')
            self.shell.DragAcceptFiles(hwnd,True)

    def close(self):
        self.closed=True
        if self.delivery_timer is not None:
            self.root.after_cancel(self.delivery_timer); self.delivery_timer=None
        if self.pending is not None:
            self.root.after_cancel(self.pending); self.pending=None
        if getattr(self,'map_binding',None):
            self.root.unbind('<Map>',self.map_binding); self.map_binding=None
        for hwnd in list(self.handles):
            self.shell.DragAcceptFiles(hwnd,False)
            if self.elevated:
                for message in (0x233,0x49): self.user.ChangeWindowMessageFilterEx(hwnd,message,0,None)
            self.common.RemoveWindowSubclass(hwnd,self.handler,self.identifier)
        self.handles.clear()
        self.hwnd=None
