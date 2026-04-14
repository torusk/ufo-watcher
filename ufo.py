"""macOSのUFOウィンドウとアニメーション — pyobjc-framework-Cocoa を使用。"""

import math
import os
import threading
import webbrowser

import AppKit
import objc
from Cocoa import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSApplication,
    NSApplicationActivationPolicyAccessory,  # Dockに表示しないポリシー
    NSBackingStoreBuffered,
    NSColor,
    NSImageScaleProportionallyUpOrDown,
    NSImageView,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSTextField,
    NSTimer,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,  # 全Spacesに表示
    NSWindowCollectionBehaviorStationary,         # Mission Controlで動かない
    NSWindowStyleMaskBorderless,
)
from Foundation import NSUserNotification, NSUserNotificationCenter


# ── アニメーション定数 ──────────────────────────────────────────────────────
_UFO_SIZE = 96             # UFO画像の表示サイズ（px）
_WOBBLE_AMP = 3.0          # アイドル時のサイン波ホバー振幅（px）
_WOBBLE_FREQ = 0.6         # アイドル時のホバー周波数（Hz）
_FLY_SPEED = 2.2           # フライト時のリサージュパラメータの進む速度
_TIMER_INTERVAL = 1 / 60  # NSTimerの発火間隔（秒）= 60fps
_DRAG_THRESHOLD = 4        # ドラッグ判定の最小移動距離（px）。これ以下はクリック扱い


# ---------------------------------------------------------------------------
# カスタム NSView — クリック / ダブルクリック / ドラッグ / 右クリックを処理
# ---------------------------------------------------------------------------
class UFOView(AppKit.NSView):
    """UFO画像を表示し、マウスイベントを UFOWindowController に中継するビュー。"""

    def initWithController_(self, controller):
        """コントローラへの参照を持った状態で初期化する。"""
        frame = NSMakeRect(0, 0, _UFO_SIZE, _UFO_SIZE)
        self = objc.super(UFOView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._controller = controller
        # ドラッグ開始時のマウス座標（スクリーン座標系）
        self._drag_start_mouse = None
        # ドラッグ開始時のウィンドウ左下原点
        self._drag_start_origin = None
        # mouseUp_ 時にドラッグかクリックかを判別するフラグ
        self._did_drag = False
        # ダブルクリック処理済みフラグ（mouseUp_ での誤クリック防止）
        self._is_double_click = False
        return self

    def mouseDown_(self, event):
        """マウスボタン押下イベント。ダブルクリックとシングルクリックを振り分ける。"""
        if event.clickCount() == 2:
            # ダブルクリック: URLをブラウザで開く
            self._is_double_click = True
            self._controller.handleDoubleClick()
            return
        # シングルクリック開始: ドラッグ追跡のために開始座標を記録
        self._is_double_click = False
        loc = event.locationInWindow()
        win_origin = self._controller._window.frame().origin
        # ウィンドウ座標 → スクリーン座標に変換して保存
        self._drag_start_mouse = self._controller._window.convertPointToScreen_(loc)
        self._drag_start_origin = win_origin
        self._did_drag = False

    def mouseDragged_(self, event):
        """マウスドラッグイベント。ウィンドウをマウスに追従させて移動する。"""
        if self._drag_start_mouse is None or self._is_double_click:
            return
        loc = event.locationInWindow()
        current = self._controller._window.convertPointToScreen_(loc)
        dx = current.x - self._drag_start_mouse.x
        dy = current.y - self._drag_start_mouse.y
        # 閾値を超えたらドラッグとみなす（微細なマウスブレを無視）
        if abs(dx) > _DRAG_THRESHOLD or abs(dy) > _DRAG_THRESHOLD:
            self._did_drag = True
        new_x = self._drag_start_origin.x + dx
        new_y = self._drag_start_origin.y + dy
        self._controller._window.setFrameOrigin_(AppKit.NSPoint(new_x, new_y))
        # アイドル時の基準位置（ホーム位置）も新しい場所に更新
        self._controller.setIdleHome_y_(new_x, new_y)

    def mouseUp_(self, event):
        """マウスボタン離し。ドラッグでなければシングルクリックとして処理する。"""
        if self._is_double_click:
            return  # ダブルクリックはすでに mouseDown_ で処理済み
        if not self._did_drag:
            # 動きが少なかった = クリック → UFO停止
            self._controller.handleClick()
        self._drag_start_mouse = None
        self._drag_start_origin = None

    def rightMouseDown_(self, event):
        """右クリックでコンテキストメニューを表示する。
        メニュー項目: 現在のURL（表示のみ）、URLを変更、終了
        """
        menu = NSMenu.alloc().initWithTitle_("")

        # 現在の監視URLをグレーアウトで表示（50文字を超える場合は省略）
        url = self._controller._current_url
        display = url if len(url) <= 50 else url[:47] + "…"
        label = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(display, None, "")
        label.setEnabled_(False)  # クリックできないラベルとして表示
        menu.addItem_(label)

        menu.addItem_(NSMenuItem.separatorItem())

        # URL変更ダイアログを開くメニュー項目
        change = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "URLを変更…", "changeURL:", ""
        )
        change.setTarget_(self._controller)
        menu.addItem_(change)

        menu.addItem_(NSMenuItem.separatorItem())

        # アプリ終了メニュー項目
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "終了", "quitApp:", ""
        )
        quit_item.setTarget_(self._controller)
        menu.addItem_(quit_item)

        NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self)

    def acceptsFirstResponder(self):
        """キーボードイベントを受け取れるようにする（将来の拡張用）。"""
        return True

    def isOpaque(self):
        """ビューが透明（非不透明）であることをCocoaに伝える。背景を透過させるために必要。"""
        return False


# ---------------------------------------------------------------------------
# ウィンドウコントローラ — アニメーション状態 + URL変更ロジック
# ---------------------------------------------------------------------------
class UFOWindowController(AppKit.NSObject):
    """UFOウィンドウの生成・アニメーション制御・ユーザー操作ハンドリングを担う。

    NSTimer（60fps）から tick_() が呼ばれ続け、毎フレームの位置を計算してウィンドウを移動する。
    """

    def initWithAlertEvent_flyDuration_currentUrl_onUrlChange_(
        self,
        alert_event: threading.Event,
        fly_duration: float,
        current_url: str,
        on_url_change,
    ):
        """初期化: UFOウィンドウを生成し、アイドル位置（右下）に配置する。"""
        self = objc.super(UFOWindowController, self).init()
        if self is None:
            return None

        screen = AppKit.NSScreen.mainScreen()
        vf = screen.visibleFrame()  # Dockやメニューバーを除いた有効領域
        self._sw = screen.frame().size.width   # スクリーン全体の幅（Lissajous計算用）
        self._sh = screen.frame().size.height  # スクリーン全体の高さ（Lissajous計算用）
        self._alert_event = alert_event        # Watcherからの変化通知イベント
        self._fly_duration = fly_duration      # フライトアニメーションの最大継続時間（秒）
        self._current_url = current_url        # 現在の監視URL（右クリックメニューに表示）
        self._on_url_change = on_url_change    # URL変更時に呼ぶコールバック（main.py側）
        self._tick = 0.0                       # アイドルホバーのsin波フェーズ用タイマー
        self._flying = False                   # フライト中かどうかのフラグ
        self._fly_t = 0.0                      # Lissajousパラメータt（飛行位置計算に使用）
        self._fly_elapsed = 0.0               # フライト開始からの経過時間（秒）
        self._alerted_idle = False            # 更新検知後・未確認のまま自動停止した状態（左下待機）

        # 通常アイドル位置: visibleFrame の右下隅、Dockから20px上
        self._idle_x = vf.origin.x + vf.size.width - _UFO_SIZE - 20
        self._idle_y = vf.origin.y + 20
        # 未確認アラート待機位置: 左下隅（右下と対称）
        self._alert_idle_x = vf.origin.x + 20

        # ── ウィンドウを生成 ──────────────────────────────────────────────
        frame = NSMakeRect(self._idle_x, self._idle_y, _UFO_SIZE, _UFO_SIZE)
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSWindowStyleMaskBorderless,  # タイトルバー・枠なし
            NSBackingStoreBuffered,
            False,
        )
        self._window.setOpaque_(False)                          # 透明ウィンドウを許可
        self._window.setBackgroundColor_(NSColor.clearColor())  # 背景を完全透明に
        # NSFloatingWindowLevel+1 で他のフローティングウィンドウより手前に表示
        self._window.setLevel_(AppKit.NSFloatingWindowLevel + 1)
        self._window.setHasShadow_(False)                       # 影なし（UFO画像に任せる）
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces   # 全Spacesに常に表示
            | NSWindowCollectionBehaviorStationary       # Mission Controlで移動しない
        )
        self._window.setIgnoresMouseEvents_(False)  # クリックを受け取る

        # ── UFOView（カスタムビュー）をコンテンツビューとして設定 ────────
        content_view = UFOView.alloc().initWithController_(self)
        self._window.setContentView_(content_view)

        # ── UFO画像を NSImageView に設定してビューに追加 ─────────────────
        image_path = os.path.join(os.path.dirname(__file__), "assets", "UFO.png")
        image = AppKit.NSImage.alloc().initWithContentsOfFile_(image_path)
        if image is None:
            raise FileNotFoundError(f"UFO image not found: {image_path}")
        image_view = NSImageView.alloc().initWithFrame_(NSMakeRect(0, 0, _UFO_SIZE, _UFO_SIZE))
        image_view.setImage_(image)
        image_view.setImageScaling_(NSImageScaleProportionallyUpOrDown)  # アスペクト比を保ってリサイズ
        content_view.addSubview_(image_view)

        self._window.makeKeyAndOrderFront_(None)  # ウィンドウを前面に表示
        return self

    def setIdleHome_y_(self, x, y):
        """ドラッグで移動した後のアイドルホーム位置を更新する。"""
        self._idle_x = x
        self._idle_y = y

    # ------------------------------------------------------------------
    # マウス操作ハンドラ（UFOView から呼ばれる）
    # ------------------------------------------------------------------
    def handleClick(self):
        """シングルクリック: 飛行中 or 左下待機中なら「気づいた」として右下の通常位置に戻る。"""
        if self._flying:
            self._stop_flying()
        elif self._alerted_idle:
            # 左下待機中にクリック → 確認済みとして通常状態（右下）に戻る
            self._alerted_idle = False

    def handleDoubleClick(self):
        """ダブルクリック: 監視中のURLをデフォルトブラウザで開く。"""
        webbrowser.open(self._current_url)

    def _send_notification(self):
        """macOS通知センターにページ更新を通知する。
        席を外していてUFOが見えなくても、通知履歴から気づけるようにするため。
        失敗しても動作に影響しないよう例外は握り潰す。
        """
        try:
            notification = NSUserNotification.alloc().init()
            notification.setTitle_("UFO Watcher")
            url_display = self._current_url if len(self._current_url) <= 60 else self._current_url[:57] + "…"
            notification.setInformativeText_(f"ページが更新されました\n{url_display}")
            notification.setSoundName_("NSUserNotificationDefaultSoundName")
            NSUserNotificationCenter.defaultUserNotificationCenter().deliverNotification_(notification)
        except Exception:
            pass

    def changeURL_(self, sender):
        """右クリックメニュー「URLを変更…」からURL変更ダイアログを表示する。
        OKが押されて新URLが入力されていれば on_url_change コールバックを呼ぶ。
        """
        alert = NSAlert.alloc().init()
        alert.setMessageText_("監視URLを変更")
        alert.setInformativeText_("新しいURLを入力してください。次のポーリングから反映されます。")
        alert.addButtonWithTitle_("変更")
        alert.addButtonWithTitle_("キャンセル")

        # テキストフィールドを補助ビューとしてダイアログに埋め込む
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 360, 24))
        field.setStringValue_(self._current_url)  # 現在のURLをデフォルト値として表示
        alert.setAccessoryView_(field)
        alert.window().setInitialFirstResponder_(field)
        field.selectText_(None)  # テキストを全選択状態にして入力しやすくする

        if alert.runModal() == NSAlertFirstButtonReturn:
            new_url = field.stringValue().strip()
            # 空文字や変化なしは無視する
            if new_url and new_url != self._current_url:
                self._current_url = new_url
                self._on_url_change(new_url)

    def quitApp_(self, sender):
        """右クリックメニュー「終了」からアプリを終了する。"""
        NSApplication.sharedApplication().terminate_(None)

    # ------------------------------------------------------------------
    # NSTimer コールバック（60fps）
    # ------------------------------------------------------------------
    def tick_(self, _timer):
        """メインループから毎フレーム呼ばれる。alert_event の状態に応じてアニメーションを切り替える。

        フロー:
          - alert_event がセット & 未飛行 → フライト開始
          - alert_event がセット & 飛行中 → fly_duration 経過したら自動停止
          - alert_event がクリア & 飛行中 → 即時停止（クリックで dismiss された場合など）
          - フライト中 → Lissajous曲線で画面を飛び回る
          - アイドル中 → サイン波でふわふわホバリング
        """
        self._tick += _TIMER_INTERVAL  # アイドルホバーのフェーズを進める

        if self._alert_event.is_set():
            if not self._flying:
                # アラート検出 → フライト開始（未確認フラグをリセット）
                self._flying = True
                self._fly_t = 0.0
                self._fly_elapsed = 0.0
                self._alerted_idle = False
                self._send_notification()  # 通知センターにも通知
            else:
                # 飛行継続中: 経過時間を加算して上限に達したら左下で待機
                self._fly_elapsed += _TIMER_INTERVAL
                if self._fly_elapsed >= self._fly_duration:
                    self._stop_flying_to_alert_idle()
        else:
            # アラートがクリアされた（クリック dismiss 等）なら停止
            if self._flying:
                self._stop_flying()

        # アニメーション位置の更新
        if self._flying:
            self._update_flying()
        else:
            self._update_idle()

    def _stop_flying(self):
        """フライトを停止し、alert_event もクリアして通常アイドル（右下）に戻す。
        飛行中にクリックして「その場で確認した」場合に呼ばれる。
        """
        self._flying = False
        self._alerted_idle = False
        self._alert_event.clear()

    def _stop_flying_to_alert_idle(self):
        """フライトをタイムアウトで停止し、左下の未確認待機状態に移行する。
        席を外していて気づかなかった場合、左下で待機することで変化があったことを示す。
        """
        self._flying = False
        self._alerted_idle = True
        self._alert_event.clear()

    def _update_idle(self):
        """アイドル時のホバーアニメーション: サイン波で上下に揺れる。
        通常は右下、未確認アラート待機中は左下に表示する。
        """
        dy = _WOBBLE_AMP * math.sin(2 * math.pi * _WOBBLE_FREQ * self._tick)
        x = self._alert_idle_x if self._alerted_idle else self._idle_x
        self._window.setFrameOrigin_(AppKit.NSPoint(x, self._idle_y + dy))

    def _update_flying(self):
        """フライト時のリサージュ曲線アニメーション。
        x = cx + rx * sin(3t + π/2)
        y = cy + ry * sin(2t)
        という (3,2) リサージュ図形で画面を縦横無尽に飛び回る。
        margin はUFOが画面端に隠れないようにする余白。
        """
        self._fly_t += _TIMER_INTERVAL * _FLY_SPEED  # パラメータtを進める
        t = self._fly_t
        margin = _UFO_SIZE
        cx = (self._sw - _UFO_SIZE) / 2   # 画面中心X
        cy = (self._sh - _UFO_SIZE) / 2   # 画面中心Y
        rx = cx - margin                   # X方向の振幅（画面幅の半分 - margin）
        ry = cy - margin                   # Y方向の振幅（画面高さの半分 - margin）
        x = cx + rx * math.sin(3 * t + math.pi / 2)
        y = cy + ry * math.sin(2 * t)
        self._window.setFrameOrigin_(AppKit.NSPoint(x, y))


# ---------------------------------------------------------------------------
# 公開エントリーポイント
# ---------------------------------------------------------------------------
def run_app(
    alert_event: threading.Event,
    fly_duration: float = 5.0,
    current_url: str = "",
    on_url_change=None,
):
    """Cocoaアプリを起動してメインループをブロックする。
    アプリ終了（quitApp_ or Cmd+Q）まで返らない。

    Args:
        alert_event: Watcher から変化通知を受け取る Event
        fly_duration: フライトアニメーションの最大継続秒数
        current_url: 初期監視URL（右クリックメニューに表示）
        on_url_change: URL変更時に呼ばれるコールバック (new_url: str) -> None
    """
    app = NSApplication.sharedApplication()
    # Dockアイコン・メニューバーを表示しないアクセサリポリシーで起動
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    # UFOウィンドウコントローラを生成（ウィンドウ表示も行われる）
    controller = UFOWindowController.alloc().initWithAlertEvent_flyDuration_currentUrl_onUrlChange_(
        alert_event, fly_duration, current_url, on_url_change or (lambda u: None)
    )

    # 60fps の NSTimer を登録: 毎フレーム controller.tick_() を呼び出す
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        _TIMER_INTERVAL, controller, "tick:", None, True
    )

    # Cocoaのメインイベントループ開始（ここがブロック）
    app.run()
