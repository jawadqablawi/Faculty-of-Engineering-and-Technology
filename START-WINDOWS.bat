@echo off
setlocal
cd /d "%~dp0"
title ETCS - Local Windows Preview
where docker >nul 2>&1
if errorlevel 1 (
  echo Install Docker Desktop first: https://www.docker.com/products/docker-desktop/
  echo Then open Docker Desktop and run this file again.
  pause
  exit /b 1
)
docker info >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop is not running. Open it and wait until it is ready.
  pause
  exit /b 1
)
echo Preparing ETCS. The first launch downloads dependencies and may take several minutes.
docker compose -p etcs-windows -f compose.windows.yaml up --build --detach --wait --wait-timeout 120
if errorlevel 1 goto failed
echo Create your coordinator account on the first launch.
echo Password characters will be hidden while you type. This is normal.
docker compose -p etcs-windows -f compose.windows.yaml exec web python manage.py bootstrap --interactive
if errorlevel 1 goto failed
start "" "http://localhost:8000"
echo ETCS is running on this computer at http://localhost:8000
echo Login using your own email and password.
echo STOP-WINDOWS.bat stops the application without deleting your data.
pause
exit /b 0
:failed
echo Setup did not finish. Keep this window open to read the error above.
pause
exit /b 1
