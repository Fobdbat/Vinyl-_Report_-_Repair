# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: genera dist\VinylPremaster\ (carpeta amb VinylPremaster.exe).
# Python 3.8 de 64 bits: funciona a Windows 7, 8, 10 i 11 de 64 bits.
# Es fa en carpeta (no en un sol .exe) perquè arrenqui ràpid: numpy i scipy són grans.
import os
from PyInstaller.utils.hooks import collect_data_files

datas = [
    (os.path.join("assets", "vinylpremaster.ico"), "assets"),
    (os.path.join("assets", "vinylpremaster.png"), "assets"),
]
for src, dst in collect_data_files("tkinterdnd2"):
    low = src.replace("\\", "/").lower()
    if "/osx-" in low or "/linux-" in low or "/win-arm64" in low or "/win-x86" in low:
        continue
    datas.append((src, dst))

a = Analysis(
    ["VinylPremaster.pyw"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["tkinterdnd2", "tkinterdnd2.TkinterDnD", "scipy.signal", "scipy.interpolate",
                   "scipy.ndimage", "soundfile", "sounddevice"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "PIL", "pandas", "IPython", "pytest", "sphinx"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VinylPremaster",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join("assets", "vinylpremaster.ico"),
    version="version_info.txt",
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name="VinylPremaster")
