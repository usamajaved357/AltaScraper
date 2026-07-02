#!/bin/bash
# ============================================================
#  Listing Generator Suite - one-click launcher (macOS)
#
#  HOW TO USE:  Just double-click this file.
#
#  - First run: it creates a private Python environment and
#    installs everything the app needs (this takes a few minutes,
#    ONE TIME only). You'll see progress in the window.
#  - Every run after that: it starts instantly.
#  - Your browser opens automatically at http://127.0.0.1:5000
#  - To STOP the app: press Ctrl+C in this window, or close it.
# ============================================================

# --- Move into the folder this script lives in, whatever the path. ---
cd "$(dirname "$0")" || exit 1

echo "============================================================"
echo "  Listing Generator Suite"
echo "============================================================"
echo

# --- 1. Find a Python 3 to build the environment with. -------------
# Prefer 3.11, then any python3. The bundled installer (python-3.14.6-
# macos11.pkg) in this folder can be used if none is found.
if command -v python3.11 >/dev/null 2>&1; then
  PY=python3.11
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  echo "ERROR: Python 3 is not installed on this Mac."
  echo
  echo "Fix: double-click the file 'python-3.14.6-macos11.pkg' in this"
  echo "same folder, finish the installer, then double-click START_APP again."
  echo
  read -n 1 -s -r -p "Press any key to close."
  exit 1
fi
echo "Using system Python: $($PY --version 2>&1)"
echo

# --- 2. Create the private virtual environment on first run. -------
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "First-time setup: creating a private Python environment..."
  "$PY" -m venv "$VENV_DIR" || {
    echo "ERROR: could not create the environment."
    read -n 1 -s -r -p "Press any key to close."
    exit 1
  }
fi

# Use the venv's own python/pip from here on.
VPY="$VENV_DIR/bin/python"

# --- 3. Install / verify dependencies. -----------------------------
# We use a stamp file so the slow install only happens when
# requirements.txt actually changes, not on every launch.
STAMP="$VENV_DIR/.deps_installed"
NEED_INSTALL=0
if [ ! -f "$STAMP" ]; then
  NEED_INSTALL=1
elif [ requirements.txt -nt "$STAMP" ]; then
  NEED_INSTALL=1
fi

if [ "$NEED_INSTALL" -eq 1 ]; then
  echo "Installing required packages (first run can take a few minutes)..."
  echo "------------------------------------------------------------"
  "$VPY" -m pip install --upgrade pip
  if "$VPY" -m pip install -r requirements.txt; then
    date > "$STAMP"
    echo "------------------------------------------------------------"
    echo "All packages installed successfully."
  else
    echo "------------------------------------------------------------"
    echo "ERROR: some packages failed to install. See messages above."
    echo "You can re-run START_APP to try again."
    read -n 1 -s -r -p "Press any key to close."
    exit 1
  fi
  echo
fi

# --- 4. Open the browser once the app reports its port. ------------
# The app writes its chosen port to .app_port (may not be 5000 if
# macOS AirPlay Receiver is using 5000). Wait for it, then open.
rm -f .app_port
(
  PORT=5000
  for _i in $(seq 1 40); do
    if [ -f .app_port ]; then PORT="$(cat .app_port)"; break; fi
    sleep 0.5
  done
  open "http://127.0.0.1:${PORT}"
) &

# --- 5. Launch the dashboard. --------------------------------------
echo "============================================================"
echo "  Starting the app. Keep this window OPEN while you use it."
echo "  To STOP: press Ctrl+C here, or close this window."
echo "============================================================"
echo
"$VPY" dashboard.py

echo
echo "============================================================"
echo "  The app has stopped. You can close this window."
echo "============================================================"
read -n 1 -s -r -p "Press any key to close."
