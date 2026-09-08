#!/usr/bin/env bash
# MOONDROP EDGE PC 控制器 (GUI)
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "[setup] creating venv and installing dependencies..."
  python3 -m venv .venv
  .venv/bin/python -m pip install -U pip
  .venv/bin/python -m pip install -r requirements-gui.txt
fi
exec .venv/bin/python -m moondrop_link.gui "$@"
