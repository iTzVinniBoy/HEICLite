"""Empacotamento Windows com temas e ícone incluídos."""
import app  # Configura Tcl/Tk antes da análise do PyInstaller.
import PyInstaller.__main__
from version import APP_VERSION

if __name__ == '__main__':
    PyInstaller.__main__.run([
        '--noconfirm', '--clean', '--onefile', '--windowed',
        '--name', 'HEICLite', '--distpath', f'dist/versao-{APP_VERSION}',
        '--collect-all', 'customtkinter', '--add-data', 'assets;assets',
        '--icon', 'assets/heiclite.ico', 'app.py',
    ])
