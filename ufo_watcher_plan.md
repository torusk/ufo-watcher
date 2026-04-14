# UFO Watcher — 企画メモ

作成日: 2026-04-13
更新日: 2026-04-14

---

## コンセプト

指定したURLに変化があったら、デスクトップのUFOが飛び始める。
URLを設定するだけ。それだけ。

内容の確認は自分でやる。**「何か変わった」を見逃さないこと**だけが目的。

誰でもダウンロードしてすぐ使えるツールとしてGitHubで公開する。

---

## 使い方（ユーザー視点）

```bash
# 1. インストール
git clone https://github.com/xxx/ufo-watcher.git
cd ufo-watcher
uv sync

# 2. 設定（config.json を編集）
{
  "url": "https://example.com/news",
  "interval_sec": 60
}

# 3. 起動
uv run python main.py
```

これだけでUFOがデスクトップに常駐し、ページに変化があれば飛び始める。
クリックすれば止まる。

---

## UFOの挙動

- **平常時**: 画面上に静止（微小なホバリングのみ）
- **変化検出時**: 画面内を飛び回る
- **確認後**: クリックで静止に戻る（既読扱い）

---

## 更新検知の仕組み

シンプルなハッシュ比較。URLの中身を取得して、前回と変わったかどうかだけを見る。

```
取得: HTTP GET → レスポンスボディ
比較: hash(今回) != hash(前回) → 変化あり
記録: 今回のハッシュを保持 → 次回比較に使う
```

- ハッシュは `hashlib.sha256` でレスポンスボディ全体から生成
- 初回起動時は「現在の状態」を記録するだけ（アラートなし）
- ヘッダー・Cookie・動的な広告等でノイズが出る場合は、後述のフィルタで対応

### ノイズ対策（オプション）

ページによっては、中身が変わっていなくてもタイムスタンプや広告が変化して
誤検知する場合がある。config.json でフィルタを設定できるようにする。

```json
{
  "url": "https://example.com/news",
  "interval_sec": 60,
  "selector": "#main-content",
  "ignore_patterns": ["timestamp", "ad-banner"]
}
```

- `selector`: 監視対象をページの一部に限定（CSSセレクタ）
- `ignore_patterns`: マッチする行を比較から除外

ただし、これらはオプション。何も設定しなければページ全体のハッシュ比較で動く。

---

## config.json

```json
{
  "url": "https://www.release.tdnet.info/inbs/I_list_001_{date}.html",
  "interval_sec": 60,
  "schedule": {
    "enabled": false,
    "weekdays_only": true,
    "start": "09:00",
    "end": "15:30"
  }
}
```

| キー | 必須 | 説明 |
|---|---|---|
| `url` | ○ | 監視対象のURL |
| `interval_sec` | ○ | ポーリング間隔（秒） |
| `schedule.enabled` | - | true にすると時間帯制限を有効化 |
| `schedule.weekdays_only` | - | 平日のみ監視 |
| `schedule.start` / `end` | - | 監視時間帯 |
| `selector` | - | 監視範囲をCSSセレクタで限定 |
| `ignore_patterns` | - | 除外パターン（文字列の配列） |

`schedule` はデフォルトで無効。有効にしなければ24時間監視する。
TDnetのように市場時間だけ見たい人が使う想定。

---

## システム構成

```
ufo-watcher/
├── main.py          # エントリポイント
├── ufo.py           # UFO表示・アニメーション（メインスレッド）
├── watcher.py       # URL監視（監視スレッド）
├── config.json      # 設定
├── assets/
│   └── UFO.png      # UFO画像（透過PNG）
├── pyproject.toml
└── README.md
```

ファイル数は最小限。1ファイルで監視ロジックが完結する。

### 内部構造

1プロセス・2スレッド。

```
メインスレッド                     監視スレッド
───────────                    ───────────
NSTimer (60fps)                GET url → hash
  │                               │
  ├─ event.is_set()? ←──── YES ── hash変化 → event.set()
  │   → 浮遊アニメーション          │
  │                            sleep(interval_sec)
  ├─ クリック検出?                  │
  │   → event.clear()          繰り返し
  │   → 静止に戻す
  │
  繰り返し
```

通信: `threading.Event`（ファイルフラグは使わない）

---

## UFO表示の実装詳細

macOS上で「背景が透明なUFO画像だけが浮いている」表示を実現する。
既存の `ufo_app.py` の実装パターンを参考にする。

### ウィンドウ設定

- `NSWindow` + `NSWindowStyleMaskBorderless`（タイトルバーなし）
- `setOpaque_(False)` + `NSColor.clearColor()`（完全透過）
- `setLevel_(25)` 相当（常に最前面）
- `setHasShadow_(False)`（ウィンドウ影なし）
- `NSWindowCollectionBehaviorCanJoinAllSpaces | Stationary`（全デスクトップに表示）

### アニメーション

| 状態 | 動き | 負荷 |
|---|---|---|
| 静止（平常時） | 微小な上下揺れ（sin波、振幅2〜3px） | 極小 |
| 浮遊（変化検出時） | リサージュ曲線風の軌道で画面内を飛び回る | 低 |

- `NSTimer` で 60fps（16ms間隔）
- `setFrameOrigin_` でウィンドウ座標を更新
- 静止時は wobble のみなので CPU 負荷はほぼゼロ

### クリックで停止

- 浮遊中: `setIgnoresMouseEvents_(False)` → クリック受付
- 静止中: `setIgnoresMouseEvents_(True)` → マウス透過（デスクトップ操作を妨げない）
- クリック → `event.clear()` → 静止に戻す

### 画像

- 透過PNG、64x64〜128x128
- `NSImageView` + `NSImageScaleProportionallyUpOrDown`

---

## 常時稼働のための軽量化

一日中つけっぱなしでも問題ない設計。

| 項目 | 負荷 |
|---|---|
| 通信 | 60秒に1回の GET。ページサイズ次第だが大半は数十KB/回 |
| CPU | 静止時: sin計算のみ。浮遊時: sin + cos + 座標更新。いずれも無視できるレベル |
| メモリ | 前回のハッシュ値（32バイト）を保持するだけ |

---

## 技術スタック

- Python 3.9+（`uv` で管理）
- `pyobjc-framework-Cocoa` — macOS ウィンドウ表示
- 標準ライブラリのみ: `urllib.request`, `hashlib`, `threading`, `json`

外部依存は `pyobjc` のみ。

---

## GitHub公開を前提とした設計

### README.md に書くこと

- スクリーンショット or GIF（UFOが飛んでる様子）
- 3ステップのセットアップ手順（clone → 設定 → 起動）
- config.json の書き方
- 使用例（「TDnetの適時開示を監視」「自分のブログの更新通知」等）

### 制約・前提

- macOS専用（`pyobjc` 依存）
- Python 3.9+
- `uv` 推奨（pipでも可）

---

## 現行 UFO プロジェクトとの関係

- **別プロジェクト**として新規作成（現行UFOには手を加えない）
- 浮遊アニメーションの実装パターンのみ参考にする
- リポジトリ名: `ufo-watcher`

---

## 開発手順

1. UFO表示を作る（静止 + ホバリング + クリック検出）
2. watcher.py を作る（URL取得 → ハッシュ比較 → Event通知）
3. 自サイトのURLで動作確認（記事投稿 → UFOが飛ぶ → クリックで止まる）
4. TDnetのURLに差し替えて動作確認
5. README.md 整備 → GitHub公開

---

## 未確認事項

- [ ] TDnetのページ構造（フレームセット内の実際の一覧URL特定）
- [ ] TDnetがJSで動的に読み込んでいないか（`urllib` で取得可能か）
- [ ] 自サイトで誤検知が起きないか（広告・タイムスタンプ等のノイズ）
- [ ] UFO画像の用意（透過PNG）
