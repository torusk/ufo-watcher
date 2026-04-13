"""UFO Watcher — エントリーポイント。
config.json を読み込み、URL監視スレッドを起動してmacOSアプリを実行する。
"""

import json
import sys
import threading
from pathlib import Path

from watcher import Watcher
from ufo import run_app

# スクリプトと同じディレクトリにある config.json を参照する
CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    """config.json を読み込んで dict で返す。
    ファイルが存在しない、または必須キーが欠けている場合は終了する。
    """
    if not CONFIG_PATH.exists():
        print("[error] config.json not found. Copy config.example.json and edit it.")
        sys.exit(1)
    with CONFIG_PATH.open() as f:
        cfg = json.load(f)
    # url と interval_sec は必須
    if "url" not in cfg or "interval_sec" not in cfg:
        print("[error] config.json must contain 'url' and 'interval_sec'.")
        sys.exit(1)
    return cfg


def main():
    cfg = load_config()

    # UFOアニメーション起動の合図となるスレッドイベント
    # Watcher がセット → UFO が飛ぶ、クリックでクリア → UFO が戻る
    alert_event = threading.Event()

    # リスト経由で参照を持つのは、on_url_change コールバック内から
    # 実行中の Watcher を差し替えられるようにするため（クロージャでの再代入回避）
    watcher_holder = [Watcher(
        url=cfg["url"],
        interval_sec=int(cfg["interval_sec"]),
        alert_event=alert_event,
        selector=cfg.get("selector"),
        ignore_patterns=cfg.get("ignore_patterns", []),
        schedule=cfg.get("schedule", {}),
    )]
    watcher_holder[0].start()
    print(f"[ufo-watcher] monitoring {cfg['url']} every {cfg['interval_sec']}s")

    def on_url_change(new_url: str):
        """右クリックメニューからURLが変更されたときに呼ばれるコールバック。
        1. config.json に新URLを書き戻して永続化する
        2. 旧Watcherを停止し、新URLで新しいWatcherを起動する
        """
        # config.json を読み直して url だけ上書き（他設定は保持）
        data = json.loads(CONFIG_PATH.read_text())
        data["url"] = new_url
        CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

        # 旧Watcherを止めて新URLのWatcherを起動
        old = watcher_holder[0]
        old.stop()
        new_watcher = Watcher(
            url=new_url,
            interval_sec=int(data["interval_sec"]),
            alert_event=alert_event,
            selector=data.get("selector"),
            ignore_patterns=data.get("ignore_patterns", []),
            schedule=data.get("schedule", {}),
        )
        new_watcher.start()
        watcher_holder[0] = new_watcher
        # URL変更時はアラートをリセットしてUFOをアイドル状態に戻す
        alert_event.clear()
        print(f"[ufo-watcher] now monitoring {new_url}")

    # fly_duration_sec が未指定の場合はデフォルト5秒でUFOが飛び続ける
    fly_duration = float(cfg.get("fly_duration_sec", 5))
    try:
        # Cocoa アプリのメインループを起動（ここがブロック）
        run_app(
            alert_event,
            fly_duration=fly_duration,
            current_url=cfg["url"],
            on_url_change=on_url_change,
        )
    finally:
        # アプリ終了時に必ずWatcherスレッドを停止する
        watcher_holder[0].stop()


if __name__ == "__main__":
    main()
