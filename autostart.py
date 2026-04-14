"""UFO Watcher のログイン時自動起動を管理するスクリプト。

使い方:
    uv run python autostart.py install    # 自動起動を登録
    uv run python autostart.py uninstall  # 自動起動を解除
"""

import os
import shutil
import subprocess
import sys

_LABEL = "com.github.torusk.ufo-watcher"
_PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{_LABEL}.plist")
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG_PATH = os.path.join(_PROJECT_DIR, "ufo.log")


def _find_uv() -> str | None:
    """uv の実行パスを探す。PATH → よくあるインストール先の順で検索する。"""
    found = shutil.which("uv")
    if found:
        return found
    for candidate in (
        os.path.expanduser("~/.local/bin/uv"),
        "/opt/homebrew/bin/uv",
        "/usr/local/bin/uv",
    ):
        if os.path.isfile(candidate):
            return candidate
    return None


def _write_plist(uv: str) -> None:
    """LaunchAgents 用の plist ファイルを生成する。"""
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{uv}</string>
        <string>run</string>
        <string>python</string>
        <string>main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{_PROJECT_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{_LOG_PATH}</string>
    <key>StandardErrorPath</key>
    <string>{_LOG_PATH}</string>
</dict>
</plist>
"""
    os.makedirs(os.path.dirname(_PLIST_PATH), exist_ok=True)
    with open(_PLIST_PATH, "w") as f:
        f.write(content)


def install() -> None:
    """launchd に自動起動を登録する。"""
    uv = _find_uv()
    if not uv:
        print("エラー: uv が見つかりません。先に uv をインストールしてください。")
        print("  https://docs.astral.sh/uv/")
        sys.exit(1)

    _write_plist(uv)

    result = subprocess.run(
        ["launchctl", "load", "-w", _PLIST_PATH],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"エラー: launchctl load に失敗しました。\n{result.stderr}")
        sys.exit(1)

    print("自動起動を登録しました。次回ログイン時から自動的に起動します。")
    print(f"  plist : {_PLIST_PATH}")
    print(f"  ログ  : {_LOG_PATH}")


def uninstall() -> None:
    """launchd から自動起動の登録を解除し、plist を削除する。"""
    if not os.path.exists(_PLIST_PATH):
        print("自動起動は登録されていません。")
        return

    subprocess.run(
        ["launchctl", "unload", "-w", _PLIST_PATH],
        capture_output=True,
    )
    os.remove(_PLIST_PATH)
    print("自動起動の登録を解除しました。")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("install", "uninstall"):
        print("使い方: python autostart.py install | uninstall")
        sys.exit(1)

    if sys.argv[1] == "install":
        install()
    else:
        uninstall()
