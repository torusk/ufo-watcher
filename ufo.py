"""macOS UFO window and animation via pyobjc-framework-Cocoa."""

import math
import os
import threading

import AppKit
import objc
from Cocoa import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSColor,
    NSImageScaleProportionallyUpOrDown,
    NSImageView,
    NSMakeRect,
    NSTimer,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
)


_UFO_SIZE = 96          # px
_WOBBLE_AMP = 3.0       # idle hover amplitude (px)
_WOBBLE_FREQ = 0.6      # idle hover frequency (Hz)
_FLY_SPEED = 2.2        # flying speed multiplier
_TIMER_INTERVAL = 1 / 60


# ---------------------------------------------------------------------------
# Custom NSView — intercepts mouseDown_ to dismiss the UFO
# ---------------------------------------------------------------------------
class UFOView(AppKit.NSView):
    """Transparent content view that forwards clicks to the controller."""

    def initWithController_(self, controller):
        frame = NSMakeRect(0, 0, _UFO_SIZE, _UFO_SIZE)
        self = objc.super(UFOView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._controller = controller
        return self

    def mouseDown_(self, event):
        self._controller.handleClick()

    def acceptsFirstResponder(self):
        return True

    def isOpaque(self):
        return False


# ---------------------------------------------------------------------------
# Window controller — owns animation state
# ---------------------------------------------------------------------------
class UFOWindowController(AppKit.NSObject):
    """Manages the transparent UFO window and its animation state."""

    def initWithAlertEvent_(self, alert_event: threading.Event):
        self = objc.super(UFOWindowController, self).init()
        if self is None:
            return None

        screen = AppKit.NSScreen.mainScreen()
        sf = screen.frame()
        self._sw = sf.size.width
        self._sh = sf.size.height
        self._alert_event = alert_event
        self._tick = 0.0
        self._flying = False
        self._fly_t = 0.0

        # Build borderless transparent window
        initial_x = (self._sw - _UFO_SIZE) / 2
        initial_y = self._sh * 0.85
        frame = NSMakeRect(initial_x, initial_y, _UFO_SIZE, _UFO_SIZE)

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
        self._window.setIgnoresMouseEvents_(True)

        # Custom content view
        content_view = UFOView.alloc().initWithController_(self)
        self._window.setContentView_(content_view)

        # UFO image inside content view
        image_path = os.path.join(os.path.dirname(__file__), "assets", "UFO.png")
        image = AppKit.NSImage.alloc().initWithContentsOfFile_(image_path)
        if image is None:
            raise FileNotFoundError(f"UFO image not found: {image_path}")
        image_view = NSImageView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _UFO_SIZE, _UFO_SIZE)
        )
        image_view.setImage_(image)
        image_view.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        content_view.addSubview_(image_view)

        self._window.makeKeyAndOrderFront_(None)
        return self

    # ------------------------------------------------------------------
    # Click handler called by UFOView
    # ------------------------------------------------------------------
    def handleClick(self):
        if self._flying:
            self._alert_event.clear()

    # ------------------------------------------------------------------
    # Timer callback (60 fps)
    # ------------------------------------------------------------------
    def tick_(self, _timer):
        self._tick += _TIMER_INTERVAL

        if self._alert_event.is_set():
            if not self._flying:
                self._flying = True
                self._fly_t = 0.0
                self._window.setIgnoresMouseEvents_(False)
        else:
            if self._flying:
                self._flying = False
                self._window.setIgnoresMouseEvents_(True)

        if self._flying:
            self._update_flying()
        else:
            self._update_idle()

    def _update_idle(self):
        base_x = (self._sw - _UFO_SIZE) / 2
        base_y = self._sh * 0.85
        dy = _WOBBLE_AMP * math.sin(2 * math.pi * _WOBBLE_FREQ * self._tick)
        self._window.setFrameOrigin_(AppKit.NSPoint(base_x, base_y + dy))

    def _update_flying(self):
        self._fly_t += _TIMER_INTERVAL * _FLY_SPEED
        t = self._fly_t
        margin = _UFO_SIZE
        cx = (self._sw - _UFO_SIZE) / 2
        cy = (self._sh - _UFO_SIZE) / 2
        rx = cx - margin
        ry = cy - margin
        # Lissajous a=3, b=2, δ=π/2
        x = cx + rx * math.sin(3 * t + math.pi / 2)
        y = cy + ry * math.sin(2 * t)
        self._window.setFrameOrigin_(AppKit.NSPoint(x, y))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def run_app(alert_event: threading.Event):
    """Initialise NSApplication, create UFO window, and run the Cocoa event loop."""
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    controller = UFOWindowController.alloc().initWithAlertEvent_(alert_event)

    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        _TIMER_INTERVAL,
        controller,
        "tick:",
        None,
        True,
    )

    app.run()
