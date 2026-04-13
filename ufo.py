"""macOS UFO window and animation via pyobjc-framework-Cocoa."""

import math
import os
import threading

import AppKit
import objc
from Cocoa import (
    NSApp,
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


class UFOWindowController(AppKit.NSObject):
    """Manages the transparent UFO window and its animation state."""

    def init(self):  # noqa: A003
        self = objc.super(UFOWindowController, self).init()
        if self is None:
            return None

        screen = AppKit.NSScreen.mainScreen()
        screen_frame = screen.frame()
        sw = screen_frame.size.width
        sh = screen_frame.size.height

        self._sw = sw
        self._sh = sh
        self._alert_event: threading.Event | None = None
        self._tick = 0.0

        # Flying state
        self._flying = False
        self._fly_x = sw / 2
        self._fly_y = sh / 2
        self._fly_t = 0.0

        # Build window
        initial_x = (sw - _UFO_SIZE) / 2
        initial_y = sh * 0.85
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

        # UFO image
        image_path = os.path.join(os.path.dirname(__file__), "assets", "UFO.png")
        image = AppKit.NSImage.alloc().initWithContentsOfFile_(image_path)
        if image is None:
            raise FileNotFoundError(f"UFO image not found: {image_path}")

        image_view = NSImageView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _UFO_SIZE, _UFO_SIZE)
        )
        image_view.setImage_(image)
        image_view.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        self._window.contentView().addSubview_(image_view)
        self._window.makeKeyAndOrderFront_(None)

        return self

    def setAlertEvent_(self, event: threading.Event):
        self._alert_event = event

    # ------------------------------------------------------------------
    # Timer callback (called at 60 fps)
    # ------------------------------------------------------------------
    def tick_(self, _timer):
        self._tick += _TIMER_INTERVAL

        was_flying = self._flying
        if self._alert_event and self._alert_event.is_set():
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
        """Gentle vertical hover using a sine wave."""
        frame = self._window.frame()
        base_x = (self._sw - _UFO_SIZE) / 2
        base_y = self._sh * 0.85
        dy = _WOBBLE_AMP * math.sin(2 * math.pi * _WOBBLE_FREQ * self._tick)
        self._window.setFrameOrigin_(AppKit.NSPoint(base_x, base_y + dy))

    def _update_flying(self):
        """Lissajous-style flight across the screen."""
        self._fly_t += _TIMER_INTERVAL * _FLY_SPEED
        t = self._fly_t
        margin = _UFO_SIZE
        cx = (self._sw - _UFO_SIZE) / 2
        cy = (self._sh - _UFO_SIZE) / 2
        rx = cx - margin
        ry = cy - margin
        # Lissajous: a=3, b=2, delta=π/2 → nice figure-8-like path
        x = cx + rx * math.sin(3 * t + math.pi / 2)
        y = cy + ry * math.sin(2 * t)
        self._window.setFrameOrigin_(AppKit.NSPoint(x, y))

    # ------------------------------------------------------------------
    # Click handling (only active while flying)
    # ------------------------------------------------------------------
    def mouseDown_(self, event):
        if self._flying and self._alert_event:
            self._alert_event.clear()

    @objc.signature(b"v@:@")
    def sendEvent_(self, event):
        if event.type() == AppKit.NSEventTypeLeftMouseDown and self._flying:
            self.mouseDown_(event)
        objc.super(UFOWindowController, self).sendEvent_(event)


def run_app(alert_event: threading.Event):
    """Create the NSApplication, build the UFO window, and run the event loop."""
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    controller = UFOWindowController.alloc().init()
    controller.setAlertEvent_(alert_event)

    # Set up click forwarding: subclass content view to catch clicks
    content_view = controller._window.contentView()
    _patch_click(content_view, controller)

    timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        _TIMER_INTERVAL,
        controller,
        "tick:",
        None,
        True,
    )

    app.run()


def _patch_click(view, controller):
    """Swizzle mouseDown_ on the content view to forward clicks to controller."""

    class ClickView(type(view)):
        def mouseDown_(self, event):
            controller.mouseDown_(event)

    view.__class__ = ClickView
