#!/bin/bash
# UFO Watcher アンインストーラー
APP="$HOME/Applications/UFOWatcher.app"

# 実行中なら停止
pkill -f "ufo-catcher/main.py" 2>/dev/null && echo "Stopped running process." || true

# ログイン項目から削除
osascript -e 'tell application "System Events" to delete login item "UFO Watcher"' 2>/dev/null && echo "Removed from Login Items." || true

# app バンドルを削除
if [ -d "$APP" ]; then
    rm -rf "$APP"
    echo "Removed: $APP"
fi

echo "UFO Watcher uninstalled."
