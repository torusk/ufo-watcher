# UFO Watcher

指定したURLに変化があったら、デスクトップのUFOが飛び始めるmacOSアプリ。

- **平常時**: 画面右下でふわふわホバリング
- **変化検出時**: 画面内をリサージュ曲線で飛び回る（5秒で自動停止）
- **ダブルクリック**: 監視中のURLをブラウザで開く
- **右クリック**: URLを変更 / 終了
- **ドラッグ**: 好きな位置に移動

> macOS専用 / Python 3.9+ / 外部依存は `pyobjc` のみ

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

### オプション設定

```json
{
  "url": "https://example.com/news",
  "interval_sec": 60,
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

| キー | 必須 | 説明 |
|---|:---:|---|
| `url` | ✓ | 監視対象のURL |
| `interval_sec` | ✓ | ポーリング間隔（秒） |
| `selector` | | CSS セレクタで監視範囲を限定 |
| `ignore_patterns` | | 比較から除外するパターン（文字列配列） |
| `schedule.enabled` | | `true` で時間帯制限を有効化 |
| `schedule.weekdays_only` | | 平日のみ監視 |
| `schedule.start` / `end` | | 監視時間帯 (`"HH:MM"` 形式) |

## 起動

```bash
uv run python main.py
```

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

**自分のブログの更新通知**

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
- [uv](https://docs.astral.sh/uv/) (pip でも可: `pip install pyobjc-framework-Cocoa beautifulsoup4`)
