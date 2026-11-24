@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [Ucap] Membuat lingkungan Python .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [Ucap] Python 3.11 tidak ditemukan. Pasang dari python.org lalu coba lagi.
        pause
        exit /b 1
    )
)

echo [Ucap] Memeriksa paket...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo [Ucap] Gagal memasang paket. Periksa koneksi internet.
    pause
    exit /b 1
)

echo [Ucap] Menjalankan Ucap (lihat ikon di system tray)...
start "" ".venv\Scripts\pythonw.exe" main.py
endlocal
