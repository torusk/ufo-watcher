#!/bin/bash
# UFO Watcher インストーラー
# ~/.app バンドルを作成してログイン項目に登録する
set -euo pipefail

PROJ="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$HOME/Applications"
APP="$APP_DIR/UFOWatcher.app"

echo "Installing UFO Watcher..."

mkdir -p "$APP/Contents/MacOS"

# ランチャースクリプト（uv のフルパスを使用）
cat > "$APP/Contents/MacOS/UFOWatcher" <<LAUNCHER
#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:\$HOME/.local/bin:\$PATH"
cd "$PROJ"
exec uv run python main.py >> "\$HOME/Library/Logs/ufo_watcher.log" 2>&1
LAUNCHER
chmod +x "$APP/Contents/MacOS/UFOWatcher"

# Info.plist（LSUIElement=true で Dock・メニューバーに出ない）
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>UFOWatcher</string>
    <key>CFBundleIdentifier</key>
    <string>com.local.ufowatcher</string>
    <key>CFBundleName</key>
    <string>UFO Watcher</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
PLIST

echo "App bundle created: $APP"

# ログイン項目に追加（失敗したら手動案内）
if osascript -e "tell application \"System Events\" to make new login item at end with properties {path:\"$APP\", hidden:true}" 2>/dev/null; then
    echo "Login item registered automatically."
else
    echo ""
    echo "Automatic registration failed. Add manually:"
    echo "  System Settings > General > Login Items > +"
    echo "  Select: $APP"
    open "x-apple.systempreferences:com.apple.LoginItems-Settings.extension"
fi

echo ""
echo "Start now: open \"$APP\""
echo "Logs:      tail -f ~/Library/Logs/ufo_watcher.log"
