@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Ejecuta primero setup_windows.cmd.
  pause
  exit /b 1
)
echo Abre http://127.0.0.1:8765 en tu navegador.
echo Pulsa Ctrl+C para detener el servidor.
.venv\Scripts\python.exe run.py
pause
