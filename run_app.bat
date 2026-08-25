@echo off
setlocal
cd /d "%~dp0"
title MinFit - Local Only

set "PIP_NO_INDEX=1"
set "PIP_FIND_LINKS=%~dp0packages"
set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"
set "NO_PROXY=127.0.0.1,localhost"
set "MINFIT_SQL_SERVER=.\MINH"
set "MINFIT_SQL_DATABASE=MinFitLocal"
set "MINFIT_SQL_DRIVER=ODBC Driver 17 for SQL Server"

powershell -NoProfile -Command "$all=Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue; if(-not $all){exit 1}; $c=@($all)[0]; $p=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $c.OwningProcess); if($p.CommandLine -match 'streamlit run app.py'){exit 0}; exit 2" >nul 2>nul
if not errorlevel 1 (
  echo MinFit dang chay tai http://127.0.0.1:8501
  if /I not "%MINFIT_NO_BROWSER%"=="1" start "" "http://127.0.0.1:8501"
  exit /b 0
)

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Khong tim thay Python local trong PATH.
  echo May nay can Python 3.13 de dung bo goi offline da kem san.
  pause
  exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Bo offline nay duoc dong goi cho Python 3.13 Windows 64-bit.
  pause
  exit /b 1
)

if not exist "packages\streamlit-*.whl" (
  echo [ERROR] Thieu kho thu vien offline trong thu muc packages.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Tao moi truong Python local...
  python -m venv .venv
  if errorlevel 1 goto :failed
)

echo [2/4] Kiem tra thu vien local...
".venv\Scripts\python.exe" -c "import streamlit, pandas, pyodbc" >nul 2>nul
if errorlevel 1 (
  echo Cai Streamlit va SQL driver Python tu kho offline...
  ".venv\Scripts\python.exe" -m pip install --no-index --find-links "%~dp0packages" streamlit pyodbc
  if errorlevel 1 goto :failed
)

echo [3/4] Kiem tra database SQL Server local...
".venv\Scripts\python.exe" database.py
if errorlevel 1 goto :database_failed

echo [4/4] Mo MinFit local tai http://127.0.0.1:8501
if /I not "%MINFIT_NO_BROWSER%"=="1" start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8501'"
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
exit /b 0

:database_failed
echo.
echo [ERROR] Khong ket noi duoc SQL Server local .\MINH.
echo Hay mo SQL Server Configuration Manager va bat service SQL Server ^(MINH^).
pause
exit /b 1

:failed
echo.
echo [ERROR] Khong the khoi tao ung dung tu kho offline.
pause
exit /b 1
