#!/usr/bin/env bash
set -euo pipefail

APP_NAME="DLive Downloader"
SPEC_FILE="packaging/macos/dlive_downloader.spec"
DIST_DIR="dist"
DMG_NAME="${APP_NAME// /-}.dmg"

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "pyinstaller not found. Install it with 'pip install pyinstaller'." >&2
  exit 1
fi

pyinstaller --clean "$SPEC_FILE"

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
