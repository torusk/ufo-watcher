# UFO Watcher

指定したURLのコンテンツが変化したら、デスクトップのUFOが飛び始めるmacOS常駐アプリ。

- **平常時**: 画面右下でサイン波でふわふわホバリング
- **変化検出時**: macOS通知センターに通知 + 画面内をリサージュ曲線（3:2）で飛び回る
  - 飛行中にクリック → 確認済みとして右下に戻る
  - `fly_duration_sec` 秒経過しても無視されたら → **画面左下**に移動して待機（未確認サイン）
- **左下待機中にクリック**: 「気づいた」として右下の通常位置に戻る
- **ダブルクリック**: 監視中のURLをデフォルトブラウザで開く
- **右クリック**: URLをその場で変更 / 終了
- **ドラッグ**: UFOを好きな位置に移動（次回起動まで保持）

> macOS専用 / Python 3.9+ / 外部依存は `pyobjc-framework-Cocoa` と `beautifulsoup4` のみ

---

## セットアップ

```bash
git clone https://github.com/torusk/ufo-watcher.git
cd ufo-watcher
uv sync
```

## 設定

```bash
cp config.example.json config.json
```

`config.json` を編集:

```json
{
  "url": "https://example.com/news",
  "interval_sec": 60
}
```

### 全オプション

```json
{
  "url": "https://example.com/news",
  "interval_sec": 60,
  "fly_duration_sec": 5,
  "selector": "#main-content",
  "ignore_patterns": ["timestamp", "ad-banner"],
  "schedule": {
    "enabled": true,
    "weekdays_only": true,
    "start": "09:00",
    "end": "15:30"
  }
}
```

| キー | 必須 | デフォルト | 説明 |
|---|:---:|:---:|---|
| `url` | ✓ | — | 監視対象のURL |
| `interval_sec` | ✓ | — | ポーリング間隔（秒） |
| `fly_duration_sec` | | `5` | 変化検出後のフライト継続時間（秒） |
| `selector` | | — | CSS セレクタで監視範囲を限定（BeautifulSoup使用） |
| `ignore_patterns` | | `[]` | 比較から除外する文字列パターン（タイムスタンプ等のノイズ対策） |
| `schedule.enabled` | | `false` | `true` で時間帯・曜日制限を有効化 |
| `schedule.weekdays_only` | | `false` | `true` で平日のみ監視（土日スキップ） |
| `schedule.start` / `end` | | `"00:00"` / `"23:59"` | 監視時間帯（`"HH:MM"` 形式） |

## 起動

```bash
uv run python main.py
```

## ログ

自動起動（install.sh でインストール後）の場合、ログは以下に記録されます：

```
~/Library/Logs/ufo_watcher.log
```

**リアルタイムで確認する（ターミナルに流し続ける）**

```bash
tail -f ~/Library/Logs/ufo_watcher.log
```

`Ctrl+C` で停止。

**ログの内容例**

```
[ufo-watcher] monitoring https://example.com every 3s
[watcher] baseline recorded: a3f2c1d8…   ← 起動時のベースライン記録（アラートは出ない）
[watcher] change detected! a3f2c1d8… → 9b7e4f20…  ← 変化を検出 → UFO飛ぶ
[watcher] error: <urlopen error ...>      ← ネットワークエラー（次回まで待機）
[ufo-watcher] now monitoring https://new-url.com   ← 右クリックでURL変更後
```

**ログを消す**

```bash
# ファイルを空にする（削除せず容量だけゼロにする）
> ~/Library/Logs/ufo_watcher.log

# ファイルごと削除する
rm ~/Library/Logs/ufo_watcher.log
```

> **Note**: ターミナルから起動した場合（`uv run python main.py`）はターミナルに直接出力されるため、ログファイルは作られません。

## 動作の仕組み

```
メインスレッド (NSTimer @ 60fps)          Watcherスレッド
─────────────────────────────             ─────────────────────
alert_event.is_set() を確認    ←── YES ── ハッシュ変化 → event.set()
  → フライトアニメーション開始              │
クリック検出                               sleep(interval_sec)
  → event.clear() → アイドルへ             └─ ループ
```

- **`main.py`**: `config.json` を読み込み、Watcherスレッドを起動してCocoaアプリを実行
- **`watcher.py`**: URLをポーリングしてSHA-256ハッシュを比較する監視スレッド
  - 初回フェッチはベースライン記録のみ（アラートは発火しない）
  - `selector` でCSS選択、`ignore_patterns` でノイズ行を除外してからハッシュ化
  - `schedule` 設定に従って監視時間帯・曜日を制限
- **`ufo.py`**: macOSウィンドウとアニメーションの実装（pyobjc使用）
  - `NSWindowStyleMaskBorderless` + `clearColor` で完全透明のフロートウィンドウ
  - `NSFloatingWindowLevel+1` で常に最前面、全Spacesに表示
  - アイドル: サイン波ホバー（±3px）。変化検出時: (3,2)リサージュ曲線で飛び回る
  - 右クリックメニューからURLをその場で変更可能（`config.json` に自動書き戻し）

## 使用例

**TDnet（東証適時開示）を平日の市場時間だけ監視する**

```json
{
  "url": "https://www.release.tdnet.info/inbs/I_list_001_20240101.html",
  "interval_sec": 60,
  "schedule": {
    "enabled": true,
    "weekdays_only": true,
    "start": "09:00",
    "end": "15:30"
  }
}
```

**ブログの更新をセレクタ指定で監視する**

```json
{
  "url": "https://yourblog.example.com/",
  "interval_sec": 300,
  "selector": "article",
  "ignore_patterns": ["views", "updated"]
}
```

## 動作環境

- macOS 12 Monterey 以降
- Python 3.9+
- [uv](https://docs.astral.sh/uv/)（pip でも可: `pip install pyobjc-framework-Cocoa beautifulsoup4`）
