@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (set "DSW_PYTHON=python") else (set "DSW_PYTHON=py -3")
%DSW_PYTHON% -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] < (3,15) else 1)"
if errorlevel 1 goto python_error
if not exist ".venv\Scripts\python.exe" %DSW_PYTHON% -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.lock
if errorlevel 1 goto failed
if not exist .env copy .env.example .env >nul
echo.
echo Instalacion completada. Ejecuta start_windows.cmd.
echo Para activar la IA, configura OPENAI_API_KEY y OPENAI_MODEL en .env.
pause
exit /b 0
:python_error
echo Necesitas Python 3.11 a 3.14. Se recomienda Python 3.12 para reproducir la validacion.
pause
exit /b 1
:failed
echo La instalacion no ha terminado. Revisa el error mostrado arriba.
pause
exit /b 1
