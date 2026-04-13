"""URL監視スレッド — URLをポーリングしてコンテンツが変化したら threading.Event をセットする。"""

import hashlib
import threading
import time
import urllib.request
from datetime import datetime, time as dtime
from typing import Optional


def _fetch_body(url: str) -> bytes:
    """指定URLにGETリクエストを送り、レスポンスボディをbytesで返す。
    タイムアウトは15秒。User-Agentを明示してブロックされにくくしている。
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ufo-watcher/0.1 (github.com/torusk/ufo-watcher)"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def _extract(body: bytes, selector: Optional[str], ignore_patterns: list[str]) -> bytes:
    """ハッシュ対象のテキストを抽出・整形して返す。

    1. selector が指定されていれば BeautifulSoup でCSS選択してテキスト化
       （selector未指定 or BeautifulSoup未インストールならHTML全体をデコード）
    2. ignore_patterns に含まれる文字列を含む行を除外
       （タイムスタンプや広告など変化ノイズを除くため）
    最終的に bytes にエンコードして返す。
    """
    if selector:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(body, "html.parser")
            # CSSセレクタに一致するノードのテキストを改行区切りで結合
            nodes = soup.select(selector)
            text = "\n".join(n.get_text() for n in nodes)
        except Exception:
            # BeautifulSoupがない or パース失敗 → HTML全体で代替
            text = body.decode("utf-8", errors="replace")
    else:
        # selector 未指定: HTML全体をそのままテキスト化
        text = body.decode("utf-8", errors="replace")

    if ignore_patterns:
        # いずれかのパターン文字列を含む行を除去する（部分一致）
        lines = [
            line for line in text.splitlines()
            if not any(pat in line for pat in ignore_patterns)
        ]
        text = "\n".join(lines)

    return text.encode()


def _sha256(data: bytes) -> str:
    """bytesのSHA-256ハッシュを16進数文字列で返す。変化検出に使用する。"""
    return hashlib.sha256(data).hexdigest()


def _is_active(schedule: dict) -> bool:
    """スケジュール設定に従って、今この瞬間に監視を実行すべきかを返す。

    - schedule.enabled が False（またはキーなし）なら常に True（制限なし）
    - weekdays_only が True かつ土日なら False
    - 現在時刻が start〜end の範囲外なら False
    """
    if not schedule.get("enabled", False):
        return True  # スケジュール機能オフ → 常時監視

    now = datetime.now()
    # 土曜(5)・日曜(6)は除外
    if schedule.get("weekdays_only", False) and now.weekday() >= 5:
        return False

    # "HH:MM" 形式の文字列を time オブジェクトに変換して比較
    start_str = schedule.get("start", "00:00")
    end_str = schedule.get("end", "23:59")
    start = dtime(*map(int, start_str.split(":")))
    end = dtime(*map(int, end_str.split(":")))
    return start <= now.time() <= end


class Watcher(threading.Thread):
    """バックグラウンドでURLをポーリングし、変化があれば alert_event をセットするスレッド。

    スレッドはdaemon=Trueで起動するため、メインプロセス終了時に自動で終了する。
    明示的に止めたい場合は stop() を呼ぶ。
    """

    def __init__(
        self,
        url: str,
        interval_sec: int,
        alert_event: threading.Event,
        selector: Optional[str] = None,
        ignore_patterns: Optional[list[str]] = None,
        schedule: Optional[dict] = None,
    ):
        super().__init__(daemon=True)
        self.url = url
        self.interval_sec = interval_sec
        self.alert_event = alert_event
        self.selector = selector
        self.ignore_patterns = ignore_patterns or []
        self.schedule = schedule or {}
        # stop() で set されると run() ループが終了する
        self._stop_event = threading.Event()

    def stop(self):
        """スレッドに停止を通知する。sleep中でも即座に抜け出させる。"""
        self._stop_event.set()

    def run(self):
        """ポーリングループ本体。interval_sec 秒ごとにURLをフェッチしてハッシュを比較する。

        初回フェッチはベースラインとして記録するだけでアラートは発火しない。
        ハッシュが変化した場合のみ alert_event.set() でUFOアニメーションを起動する。
        """
        prev_hash: Optional[str] = None

        while not self._stop_event.is_set():
            # スケジュール範囲外なら30秒待って再チェック（CPUを使い続けない）
            if not _is_active(self.schedule):
                self._stop_event.wait(timeout=30)
                continue

            try:
                body = _fetch_body(self.url)
                # CSS選択 + ノイズ除去したテキストをハッシュ対象にする
                target = _extract(body, self.selector, self.ignore_patterns)
                current_hash = _sha256(target)

                if prev_hash is None:
                    # 初回: ベースラインを記録するだけでアラートは出さない
                    prev_hash = current_hash
                    print(f"[watcher] baseline recorded: {current_hash[:8]}…")
                elif current_hash != prev_hash:
                    # ハッシュが変化 → UFOアニメーションを起動
                    print(f"[watcher] change detected! {prev_hash[:8]}… → {current_hash[:8]}…")
                    prev_hash = current_hash
                    self.alert_event.set()

            except Exception as exc:
                # ネットワークエラーなどは無視して次のポーリングを待つ
                print(f"[watcher] error: {exc}")

            # interval_sec 秒待機（stop() が呼ばれたらすぐ抜ける）
            self._stop_event.wait(timeout=self.interval_sec)
