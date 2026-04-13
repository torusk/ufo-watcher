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
_DRAG_THRESHOLD = 4     # px — movement larger than this is treated as a drag, not a click


# ---------------------------------------------------------------------------
# Custom NSView — handles click (dismiss) and drag (reposition)
# ---------------------------------------------------------------------------
class UFOView(AppKit.NSView):

    def initWithController_(self, controller):
        frame = NSMakeRect(0, 0, _UFO_SIZE, _UFO_SIZE)
        self = objc.super(UFOView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._controller = controller
        self._drag_start_mouse = None   # NSPoint in screen coords at mouseDown
        self._drag_start_origin = None  # window origin at mouseDown
        self._did_drag = False
        return self

    def mouseDown_(self, event):
        # Record starting positions for potential drag
        loc = event.locationInWindow()
        win_origin = self._controller._window.frame().origin
        # Convert to screen coords
        self._drag_start_mouse = self._controller._window.convertPointToScreen_(loc)
        self._drag_start_origin = win_origin
        self._did_drag = False

    def mouseDragged_(self, event):
        if self._drag_start_mouse is None:
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
        # Update idle home to the dragged position
        self._controller.setIdleHome_y_(new_x, new_y)

    def mouseUp_(self, event):
        if not self._did_drag:
            self._controller.handleClick()
        self._drag_start_mouse = None
        self._drag_start_origin = None

    def acceptsFirstResponder(self):
        return True

    def isOpaque(self):
        return False


# ---------------------------------------------------------------------------
# Window controller — owns animation state
# ---------------------------------------------------------------------------
class UFOWindowController(AppKit.NSObject):

    def initWithAlertEvent_flyDuration_(self, alert_event: threading.Event, fly_duration: float):
        self = objc.super(UFOWindowController, self).init()
        if self is None:
            return None

        screen = AppKit.NSScreen.mainScreen()
        # visibleFrame excludes Dock and menu bar
        vf = screen.visibleFrame()
        self._sw = screen.frame().size.width
        self._sh = screen.frame().size.height
        self._alert_event = alert_event
        self._fly_duration = fly_duration
        self._tick = 0.0
        self._flying = False
        self._fly_t = 0.0
        self._fly_elapsed = 0.0

        # Idle home: bottom-right of visible area (above Dock)
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
        # Always accept mouse events so drag works in idle too
        self._window.setIgnoresMouseEvents_(False)

        content_view = UFOView.alloc().initWithController_(self)
        self._window.setContentView_(content_view)

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

    def setIdleHome_y_(self, x: float, y: float):
        """Called by UFOView during drag to update the idle home position."""
        self._idle_x = x
        self._idle_y = y

    def handleClick(self):
        if self._flying:
            self._stop_flying()

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
        # Lissajous a=3, b=2, δ=π/2
        x = cx + rx * math.sin(3 * t + math.pi / 2)
        y = cy + ry * math.sin(2 * t)
        self._window.setFrameOrigin_(AppKit.NSPoint(x, y))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def run_app(alert_event: threading.Event, fly_duration: float = 5.0):
    """Initialise NSApplication, create UFO window, and run the Cocoa event loop."""
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    controller = UFOWindowController.alloc().initWithAlertEvent_flyDuration_(alert_event, fly_duration)

    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        _TIMER_INTERVAL,
        controller,
        "tick:",
        None,
        True,
    )

    app.run()
