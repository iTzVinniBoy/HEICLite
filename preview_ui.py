"""Capturas da própria janela para revisão visual; não acessa fotos reais."""
from pathlib import Path
from app import App
from PIL import ImageGrab
from unittest.mock import patch

app=App()
app.attributes('-topmost',True)
app.geometry('1180x760+30+30')
folder=Path('build/previews'); folder.mkdir(parents=True,exist_ok=True)

def capture(mode,theme,name):
    with patch('ui.is_admin',return_value=True): app.switch_mode(mode)
    app.set_theme(theme)
    app.poll()
    app.update()
    app.tree.insert('','end',values=('Sala de estar.heic','Conferida','4,20 MB','980 KB','77,2%','Sala de estar.jpg',r'C:\Vistorias\Apartamento 102'),tags=('ok',))
    app.update_summary(dict(before=4404019,after=1003520,converted=1))
    app.update()
    app.after(700,lambda: save(name))

def save(name):
    x,y=app.winfo_rootx(),app.winfo_rooty()
    ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height())).save(folder/(name+'.png'))
    if name=='light': capture('Vistorias','Escuro','dark')
    else: app.destroy()

app.after(500,lambda:capture('Fotos','Claro','light'))
app.mainloop()
