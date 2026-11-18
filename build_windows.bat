@echo off
REM ================================================================
REM  VinylPremaster - genera dist\VinylPremaster\VinylPremaster.exe
REM  Requisit: Python 3.8.10 de 64 bits ("Windows installer (64-bit)")
REM  https://www.python.org/downloads/release/python-3810/
REM ================================================================
setlocal
cd /d "%~dp0"
py -3.8-64 --version >nul 2>&1
if errorlevel 1 (
    echo No s'ha trobat Python 3.8 de 64 bits.
    pause
    exit /b 1
)
if not exist ".venv38-64\Scripts\python.exe" py -3.8-64 -m venv .venv38-64
call ".venv38-64\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt
if errorlevel 1 goto :error
python -m unittest discover -s tests -p "test_*.py"
if errorlevel 1 goto :error
pyinstaller --noconfirm --clean VinylPremaster.spec
if errorlevel 1 goto :error
echo.
echo  FET: carpeta dist\VinylPremaster (dins hi ha VinylPremaster.exe)
pause
exit /b 0
:error
echo  S'ha produit un error.
pause
exit /b 1
