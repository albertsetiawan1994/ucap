@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv || (echo [Ucap] Python 3.11 tidak ditemukan. & pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements-dev.txt || (pause & exit /b 1)

echo [Ucap] Menjalankan tes...
".venv\Scripts\python.exe" -m pytest -q tests || (echo [Ucap] Tes gagal, build dibatalkan. & pause & exit /b 1)

echo [Ucap] Membuat Ucap.exe (satu file, tanpa jendela konsol)...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name Ucap --icon assets\ucap.ico ^
    --hidden-import keyring.backends.Windows --hidden-import pyaudiowpatch ^
    --collect-data sounddevice ^
    --collect-data tzdata ^
    --exclude-module tkinter --exclude-module pytest ^
    main.py || (pause & exit /b 1)

echo.
echo [Ucap] Selesai: dist\Ucap.exe
endlocal
