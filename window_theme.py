"""Cores nativas da barra de título (Windows 11; fallback seguro nos anteriores)."""
import ctypes
import os
from ctypes import wintypes
import customtkinter as ctk


class ThemedToplevel(ctk.CTkToplevel):
    """Janela auxiliar com a mesma superfície e barra de título do aplicativo."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('fg_color', ('#eef2f9', '#101321'))
        super().__init__(*args, **kwargs)
        self.bind('<Map>', self._mapped, add='+')
        self._schedule_titlebar()

    def _mapped(self, event):
        if event.widget is self: self._schedule_titlebar()

    def _set_appearance_mode(self, mode_string):
        super()._set_appearance_mode(mode_string)
        self._schedule_titlebar()

    def _schedule_titlebar(self):
        pending = getattr(self, '_caption_timer', None)
        if pending: self.after_cancel(pending)
        # Aguarda o HWND e a atualização nativa de tema do CustomTkinter.
        self._caption_timer = self.after(300, self._update_titlebar)

    def _update_titlebar(self):
        self._caption_timer = None
        apply_titlebar(self, ctk.get_appearance_mode() == 'Dark')

    def destroy(self):
        pending = getattr(self, '_caption_timer', None)
        if pending: self.after_cancel(pending)
        # CTk agenda ícones e geometria sem guardar seus IDs. Janelas rápidas de
        # análise podem fechar antes desses callbacks; cancela só os desta janela.
        commands=set(getattr(self,'_tclCommands',[]) or [])
        for timer in self.tk.call('after','info'):
            script=self.tk.call('after','info',timer)[0]
            if str(script).split(' ',1)[0] in commands: self.after_cancel(timer)
        super().destroy()


def apply_titlebar(window, dark):
    if os.name != 'nt': return
    user32 = ctypes.WinDLL('user32')
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    hwnd = user32.GetAncestor(window.winfo_id(), 2)
    dwm = ctypes.WinDLL('dwmapi')
    dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    def set_value(attribute, value):
        data = wintypes.DWORD(value)
        dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data))
    def color(hex_color):
        r, g, b = bytes.fromhex(hex_color)
        return r | g << 8 | b << 16
    set_value(20, int(dark))
    set_value(35, color('101321' if dark else 'eef2f9'))
    set_value(36, color('e7edff' if dark else '293957'))
