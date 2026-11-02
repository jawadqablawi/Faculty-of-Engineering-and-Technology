@echo off
setlocal
cd /d "%~dp0"
docker compose -p etcs-windows -f compose.windows.yaml stop
if errorlevel 1 (
  echo Could not stop ETCS. Make sure Docker Desktop is running.
  pause
  exit /b 1
)
echo ETCS stopped. Your accounts and uploaded files are preserved.
pause
