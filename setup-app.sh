#!/bin/bash
# TesterBot - creates the macOS app (icon). Run this once.
#   bash setup-app.sh
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/Applications/TesterBot.app"
PYBIN="$(command -v python3 || echo /usr/bin/python3)"

echo "→ Folder : $DIR"
echo "→ Python : $PYBIN"

"$PYBIN" -c "import playwright" 2>/dev/null || {
  echo "!! playwright not found. First run: $PYBIN -m pip install -r '$DIR/requirements.txt'"; }

mkdir -p "$HOME/Applications"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>TesterBot</string>
  <key>CFBundleDisplayName</key><string>TesterBot</string>
  <key>CFBundleIdentifier</key><string>org.testerbot.ui</string>
  <key>CFBundleVersion</key><string>1.1</string>
  <key>CFBundleShortVersionString</key><string>1.1</string>
  <key>CFBundleExecutable</key><string>TesterBot</string>
  <key>CFBundleIconFile</key><string>TesterBot</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>10.13</string>
  <key>LSUIElement</key><true/>
</dict></plist>
PLIST

cat > "$APP/Contents/MacOS/TesterBot" <<LAUNCH
#!/bin/bash
# TesterBot launcher - starts the server in the background and exits at once,
# so clicking the icon opens the browser again every time.
cd "$DIR" || exit 1
mkdir -p "\$HOME/Library/Logs"
nohup "$PYBIN" testerbot_ui.py >> "\$HOME/Library/Logs/TesterBot.log" 2>&1 &
exit 0
LAUNCH
chmod +x "$APP/Contents/MacOS/TesterBot"

# --- ikon ---
if [ -f "$DIR/assets/icon.png" ] && command -v iconutil >/dev/null 2>&1; then
  TMP="$(mktemp -d)"; SET="$TMP/TesterBot.iconset"; mkdir -p "$SET"
  for s in 16 32 128 256 512; do
    sips -z $s $s "$DIR/assets/icon.png" --out "$SET/icon_${s}x${s}.png" >/dev/null 2>&1 || true
    d=$((s * 2))
    sips -z $d $d "$DIR/assets/icon.png" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null 2>&1 || true
  done
  iconutil -c icns "$SET" -o "$APP/Contents/Resources/TesterBot.icns" >/dev/null 2>&1 || true
  rm -rf "$TMP"
fi

# --- clear the quarantine flags (so Gatekeeper does not block it) ---
xattr -cr "$DIR"  >/dev/null 2>&1 || true
xattr -cr "$APP"  >/dev/null 2>&1 || true
touch "$APP"

# --- add it to the Dock ---
if [ "$1" != "--no-dock" ]; then
  if ! defaults read com.apple.dock persistent-apps 2>/dev/null | grep -q "TesterBot.app"; then
    defaults write com.apple.dock persistent-apps -array-add \
      "<dict><key>tile-data</key><dict><key>file-data</key><dict>\
<key>_CFURLString</key><string>$APP</string>\
<key>_CFURLStringType</key><integer>0</integer></dict></dict></dict>" 2>/dev/null || true
    killall Dock 2>/dev/null || true
    echo "→ Added to the Dock"
  fi
fi

echo ""
echo "✓ Ready: $APP"
echo "  To open it: the TesterBot icon in the Dock, or Cmd+Space → \"TesterBot\""
echo ""
open "$APP"
