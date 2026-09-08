@echo off
rem Moondrop EDGE PC controller (GUI)
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo [setup] creating venv and installing dependencies...
  python -m venv .venv
  .venv\Scripts\python -m pip install -U pip
  .venv\Scripts\python -m pip install -r requirements-gui.txt
)
.venv\Scripts\python.exe -m moondrop_link.gui --native %*
endlocal
