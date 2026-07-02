#!/bin/bash
# ============================================================
#  Listing Generator Suite - one-click launcher (macOS)
#
#  Double-click this file to start the dashboard. Your browser
#  opens automatically at http://127.0.0.1:<port>.
#
#  First run: it builds an isolated Python environment (.venv)
#  and installs everything from requirements.txt. That can take
#  a few minutes (crawl4ai and python-amazon-sp-api are large and
#  slow to download - that is normal, not a hang). Later runs are
#  instant because the environment is reused. If requirements.txt
#  changes, it re-installs automatically.
#
#  To STOP: press Ctrl+C in this window, or just close it.
# ============================================================

set -u

# --- Always work from the folder THIS script lives in ---------------------
cd "$(dirname "$0")" || { echo "Could not enter app folder."; exit 1; }
APP_DIR="$(pwd)"

VENV_DIR=".venv"
STAMP="$VENV_DIR/.requirements.installed"

pause_and_exit() {
  echo
  read -n 1 -s -r -p "Press any key to close this window."
  echo
  exit "${1:-1}"
}

echo "============================================================"
echo "  Listing Generator Suite"
echo "  Folder: $APP_DIR"
echo "  Keep this window OPEN while you use the app."
echo "============================================================"
echo

# --- 1. Find a Python 3.11+ interpreter -----------------------------------
# Prefer python3.11, then any newer 3.x, then the generic python3 - but only
# accept it if it is actually version 3.11 or higher.
PY=""
for cand in python3.11 python3.12 python3.13 python3.14 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,11) else 1)' 2>/dev/null; then
      PY="$cand"
      break
    fi
  fi
done

if [ -z "$PY" ]; then
  echo "ERROR: No Python 3.11 or newer was found on this Mac."
  echo
  echo "In plain English: the app needs Python (the language it is written in),"
  echo "version 3.11 or newer, and this computer does not have it yet."
  echo
  echo "Fix it one of these ways, then double-click START_APP.command again:"
  echo "  1) A Python 3.14 installer is already in this folder. Double-click:"
  echo "        python-3.14.6-macos11.pkg"
  echo "     and follow the prompts."
  echo "  2) Or with Homebrew:   brew install python@3.11"
  echo "  3) Or download from:   https://www.python.org/downloads/"
  echo
  echo "(I did not install Python for you automatically on purpose - installing"
  echo " system software is your call to make.)"
  pause_and_exit 1
fi

echo "Using Python: $("$PY" --version 2>&1)  ($(command -v "$PY"))"
echo

# --- 2. Create the isolated environment (.venv) if needed -----------------
# Also self-heal: if a .venv exists but its Python is broken (e.g. the Python
# that built it was removed/upgraded), rebuild it from scratch.
venv_python="$VENV_DIR/bin/python"
if [ ! -x "$venv_python" ] || ! "$venv_python" -c 'import sys' >/dev/null 2>&1; then
  echo "Setting up the isolated environment (.venv) ..."
  rm -rf "$VENV_DIR"
  if ! "$PY" -m venv "$VENV_DIR"; then
    echo
    echo "ERROR: Could not create the virtual environment."
    echo "Technical: '$PY -m venv $VENV_DIR' failed."
    echo "Common cause: the 'venv' module is missing from this Python build."
    echo "Fix: reinstall Python using python-3.14.6-macos11.pkg in this folder."
    pause_and_exit 1
  fi
  # Force a fresh install for a fresh environment.
  rm -f "$STAMP"
fi

# --- 3. Install / update dependencies when they are stale ------------------
# Reinstall if we never installed, or if requirements.txt is newer than the
# last successful install.
need_install=0
if [ ! -f "$STAMP" ]; then
  need_install=1
elif [ requirements.txt -nt "$STAMP" ]; then
  need_install=1
  echo "requirements.txt changed since last install - updating packages ..."
fi

if [ "$need_install" -eq 1 ]; then
  echo "Installing dependencies (first run can take a few minutes) ..."
  echo "  Tip: crawl4ai and python-amazon-sp-api are big; slow download is normal."
  echo
  "$venv_python" -m pip install --upgrade pip
  if "$venv_python" -m pip install -r requirements.txt; then
    date > "$STAMP"
    echo
    echo "Dependencies installed successfully."
  else
    echo
    echo "ERROR: Installing dependencies failed (see the messages above)."
    echo "In plain English: one of the required packages did not install."
    echo "The most common causes are no internet connection, or a package that"
    echo "has no ready-made version for this Python. Scroll up to read the exact"
    echo "package and error, fix that, then run START_APP.command again."
    pause_and_exit 1
  fi
  echo
fi

# --- 4. Open the browser once the app reports its real port ----------------
# The app writes its chosen port to .app_port (macOS AirPlay may occupy 5000,
# so the app walks upward to the next free port). Wait for that file, then open.
rm -f .app_port
(
  PORT=5000
  for _i in $(seq 1 60); do
    if [ -f .app_port ]; then PORT="$(cat .app_port 2>/dev/null)"; break; fi
    sleep 0.5
  done
  open "http://127.0.0.1:${PORT}" >/dev/null 2>&1
) &

# --- 5. Launch the dashboard ----------------------------------------------
echo "============================================================"
echo "  Starting the dashboard ... (Ctrl+C here to stop)"
echo "============================================================"
echo
"$venv_python" dashboard.py

echo
echo "============================================================"
echo "  The app has stopped. You can close this window."
echo "============================================================"
pause_and_exit 0
