"""macOS UFO window and animation via pyobjc-framework-Cocoa."""

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
    NSApplicationActivationPolicyAccessory,
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
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
)


_UFO_SIZE = 96
_WOBBLE_AMP = 3.0
_WOBBLE_FREQ = 0.6
_FLY_SPEED = 2.2
_TIMER_INTERVAL = 1 / 60
_DRAG_THRESHOLD = 4     # px — movement larger than this is a drag, not a click


# ---------------------------------------------------------------------------
# Custom NSView — click / double-click / drag / right-click
# ---------------------------------------------------------------------------
class UFOView(AppKit.NSView):

    def initWithController_(self, controller):
        frame = NSMakeRect(0, 0, _UFO_SIZE, _UFO_SIZE)
        self = objc.super(UFOView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._controller = controller
        self._drag_start_mouse = None
        self._drag_start_origin = None
        self._did_drag = False
        self._is_double_click = False
        return self

    def mouseDown_(self, event):
        if event.clickCount() == 2:
            self._is_double_click = True
            self._controller.handleDoubleClick()
            return
        self._is_double_click = False
        loc = event.locationInWindow()
        win_origin = self._controller._window.frame().origin
        self._drag_start_mouse = self._controller._window.convertPointToScreen_(loc)
        self._drag_start_origin = win_origin
        self._did_drag = False

    def mouseDragged_(self, event):
        if self._drag_start_mouse is None or self._is_double_click:
            return
        loc = event.locationInWindow()
        current = self._controller._window.convertPointToScreen_(loc)
        dx = current.x - self._drag_start_mouse.x
        dy = current.y - self._drag_start_mouse.y
        if abs(dx) > _DRAG_THRESHOLD or abs(dy) > _DRAG_THRESHOLD:
            self._did_drag = True
        new_x = self._drag_start_origin.x + dx
        new_y = self._drag_start_origin.y + dy
        self._controller._window.setFrameOrigin_(AppKit.NSPoint(new_x, new_y))
        self._controller.setIdleHome_y_(new_x, new_y)

    def mouseUp_(self, event):
        if self._is_double_click:
            return
        if not self._did_drag:
            self._controller.handleClick()
        self._drag_start_mouse = None
        self._drag_start_origin = None

    def rightMouseDown_(self, event):
        menu = NSMenu.alloc().initWithTitle_("")

        # Current URL (display only)
        url = self._controller._current_url
        display = url if len(url) <= 50 else url[:47] + "…"
        label = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(display, None, "")
        label.setEnabled_(False)
        menu.addItem_(label)

        menu.addItem_(NSMenuItem.separatorItem())

        # Change URL
        change = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "URLを変更…", "changeURL:", ""
        )
        change.setTarget_(self._controller)
        menu.addItem_(change)

        menu.addItem_(NSMenuItem.separatorItem())

        # Quit
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "終了", "quitApp:", ""
        )
        quit_item.setTarget_(self._controller)
        menu.addItem_(quit_item)

        NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self)

    def acceptsFirstResponder(self):
        return True

    def isOpaque(self):
        return False


# ---------------------------------------------------------------------------
# Window controller — animation state + URL change logic
# ---------------------------------------------------------------------------
class UFOWindowController(AppKit.NSObject):

    def initWithAlertEvent_flyDuration_currentUrl_onUrlChange_(
        self,
        alert_event: threading.Event,
        fly_duration: float,
        current_url: str,
        on_url_change,
    ):
        self = objc.super(UFOWindowController, self).init()
        if self is None:
            return None

        screen = AppKit.NSScreen.mainScreen()
        vf = screen.visibleFrame()
        self._sw = screen.frame().size.width
        self._sh = screen.frame().size.height
        self._alert_event = alert_event
        self._fly_duration = fly_duration
        self._current_url = current_url
        self._on_url_change = on_url_change
        self._tick = 0.0
        self._flying = False
        self._fly_t = 0.0
        self._fly_elapsed = 0.0

        self._idle_x = vf.origin.x + vf.size.width - _UFO_SIZE - 20
        self._idle_y = vf.origin.y + 20

        frame = NSMakeRect(self._idle_x, self._idle_y, _UFO_SIZE, _UFO_SIZE)
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setLevel_(AppKit.NSFloatingWindowLevel + 1)
        self._window.setHasShadow_(False)
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
        )
        self._window.setIgnoresMouseEvents_(False)

        content_view = UFOView.alloc().initWithController_(self)
        self._window.setContentView_(content_view)

        image_path = os.path.join(os.path.dirname(__file__), "assets", "UFO.png")
        image = AppKit.NSImage.alloc().initWithContentsOfFile_(image_path)
        if image is None:
            raise FileNotFoundError(f"UFO image not found: {image_path}")
        image_view = NSImageView.alloc().initWithFrame_(NSMakeRect(0, 0, _UFO_SIZE, _UFO_SIZE))
        image_view.setImage_(image)
        image_view.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        content_view.addSubview_(image_view)

        self._window.makeKeyAndOrderFront_(None)
        return self

    def setIdleHome_y_(self, x, y):
        self._idle_x = x
        self._idle_y = y

    # ------------------------------------------------------------------
    # Interaction handlers
    # ------------------------------------------------------------------
    def handleClick(self):
        if self._flying:
            self._stop_flying()

    def handleDoubleClick(self):
        webbrowser.open(self._current_url)

    def changeURL_(self, sender):
        alert = NSAlert.alloc().init()
        alert.setMessageText_("監視URLを変更")
        alert.setInformativeText_("新しいURLを入力してください。次のポーリングから反映されます。")
        alert.addButtonWithTitle_("変更")
        alert.addButtonWithTitle_("キャンセル")

        field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 360, 24))
        field.setStringValue_(self._current_url)
        alert.setAccessoryView_(field)
        alert.window().setInitialFirstResponder_(field)
        field.selectText_(None)

        if alert.runModal() == NSAlertFirstButtonReturn:
            new_url = field.stringValue().strip()
            if new_url and new_url != self._current_url:
                self._current_url = new_url
                self._on_url_change(new_url)

    def quitApp_(self, sender):
        NSApplication.sharedApplication().terminate_(None)

    # ------------------------------------------------------------------
    # Timer callback (60 fps)
    # ------------------------------------------------------------------
    def tick_(self, _timer):
        self._tick += _TIMER_INTERVAL

        if self._alert_event.is_set():
            if not self._flying:
                self._flying = True
                self._fly_t = 0.0
                self._fly_elapsed = 0.0
            else:
                self._fly_elapsed += _TIMER_INTERVAL
                if self._fly_elapsed >= self._fly_duration:
                    self._stop_flying()
        else:
            if self._flying:
                self._stop_flying()

        if self._flying:
            self._update_flying()
        else:
            self._update_idle()

    def _stop_flying(self):
        self._flying = False
        self._alert_event.clear()

    def _update_idle(self):
        dy = _WOBBLE_AMP * math.sin(2 * math.pi * _WOBBLE_FREQ * self._tick)
        self._window.setFrameOrigin_(AppKit.NSPoint(self._idle_x, self._idle_y + dy))

    def _update_flying(self):
        self._fly_t += _TIMER_INTERVAL * _FLY_SPEED
        t = self._fly_t
        margin = _UFO_SIZE
        cx = (self._sw - _UFO_SIZE) / 2
        cy = (self._sh - _UFO_SIZE) / 2
        rx = cx - margin
        ry = cy - margin
        x = cx + rx * math.sin(3 * t + math.pi / 2)
        y = cy + ry * math.sin(2 * t)
        self._window.setFrameOrigin_(AppKit.NSPoint(x, y))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def run_app(
    alert_event: threading.Event,
    fly_duration: float = 5.0,
    current_url: str = "",
    on_url_change=None,
):
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    controller = UFOWindowController.alloc().initWithAlertEvent_flyDuration_currentUrl_onUrlChange_(
        alert_event, fly_duration, current_url, on_url_change or (lambda u: None)
    )

    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        _TIMER_INTERVAL, controller, "tick:", None, True
    )

    app.run()
