#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_NAME="DLive Vault"
SPEC_FILE="$PROJECT_ROOT/packaging/macos/dlive_downloader.spec"
DIST_DIR="$PROJECT_ROOT/dist"
BUILD_DIR="$PROJECT_ROOT/build"
DMG_NAME="${APP_NAME// /-}.dmg"
PYI_CONFIG_DIR="${PYI_CONFIG_DIR:-$PROJECT_ROOT/.pyinstaller_config}"
PYI_CACHE_DIR="${PYI_CACHE_DIR:-$PROJECT_ROOT/.pyinstaller_cache}"
PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$PYI_CONFIG_DIR}"
PYINSTALLER_CONFIG_PATH="${PYINSTALLER_CONFIG_PATH:-$PYI_CONFIG_DIR}"
PYINSTALLER_CACHE_DIR="${PYINSTALLER_CACHE_DIR:-$PYI_CACHE_DIR}"

# Detect the Python interpreter associated with the current shell (prefers python, then python3).
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x "$PROJECT_ROOT/venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_ROOT/venv/bin/python"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    echo "Python interpreter not found. Activate your virtualenv before running this script." >&2
    exit 1
  fi
fi

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "pyinstaller not found. Install it with 'pip install pyinstaller'." >&2
  exit 1
fi

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1; then
import tkinter  # noqa: F401
PY
  cat <<'EOF' >&2
Current Python interpreter is missing Tk support (_tkinter). Install a Python build that bundles Tk (for example,
the official python.org installer or Homebrew's python-tk package) and recreate the virtual environment before
building the macOS app.
EOF
  exit 1
fi

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1; then
import customtkinter  # noqa: F401
PY
  cat <<'EOF' >&2
customtkinter is not installed in the selected interpreter ($PYTHON_BIN).
Run "pip install -r requirements.txt" inside your virtualenv before building.
EOF
  exit 1
fi

CLEAN_FLAG="--clean"
if [ -n "${SKIP_CLEAN:-}" ]; then
  CLEAN_FLAG=""
fi

mkdir -p "$DIST_DIR" "$BUILD_DIR" "$PYI_CACHE_DIR" "$PYI_CONFIG_DIR"

export PYINSTALLER_CACHE_DIR PYINSTALLER_CONFIG_DIR PYINSTALLER_CONFIG_PATH PYI_CACHE_DIR PYI_CONFIG_DIR

pyinstaller \
  ${CLEAN_FLAG} \
  --distpath "$DIST_DIR" \
  --workpath "$BUILD_DIR" \
  "$SPEC_FILE"

APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
if [ ! -d "$APP_BUNDLE" ]; then
  echo "Expected app bundle '$APP_BUNDLE' was not created." >&2
  exit 1
fi

if command -v create-dmg >/dev/null 2>&1; then
  create-dmg "$APP_BUNDLE" "$DIST_DIR" --overwrite
else
  if ! command -v hdiutil >/dev/null 2>&1; then
    echo "Neither create-dmg nor hdiutil is available. Install create-dmg via npm or run this script on macOS." >&2
    exit 1
  fi
  hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$APP_BUNDLE" \
    -ov \
    -format UDZO \
    "$DIST_DIR/$DMG_NAME"
fi

echo "Created macOS app bundle at $APP_BUNDLE"
if [ -f "$DIST_DIR/$DMG_NAME" ]; then
  echo "Created disk image at $DIST_DIR/$DMG_NAME"
else
  echo "create-dmg generated the installer inside $DIST_DIR" \
    "(see the command output above)."
fi
