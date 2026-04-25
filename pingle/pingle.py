"""
Pingle — Questboard notification daemon (Win95 styled).

Watches the /pings board activity_log and fires PyQt5 toast notifications
for ticket entry (created), move (status change), and leave (closed).

Usage:
    pythonw pingle.py          # run as background daemon
    python pingle.py --once    # fire pending notifications and exit
"""

import sys
import os
import json
import urllib.request
import winsound
import threading
import urllib.error
import webbrowser
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QHBoxLayout, QVBoxLayout, QGraphicsOpacityEffect,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QCursor, QLinearGradient, QColor, QPainter

QB_API = "https://questboard-ec2.tail7f6073.ts.net"
QB_URL = QB_API
POLL_MS = 3000
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pingle.log")
LOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pingle.lock")

# Win95 palette
W95_SURFACE = "#c0c0c0"
W95_BTN_HIGHLIGHT = "#ffffff"
W95_BTN_FACE = "#dfdfdf"
W95_BTN_SHADOW = "#808080"
W95_FRAME = "#0a0a0a"
W95_TITLE_BLUE = "#000080"
W95_TITLE_BLUE_LIGHT = "#1084d0"
W95_TEXT = "#000000"
W95_FONT = "MS Sans Serif"


def droid_chirp():
    """Play an R2-D2 style chirp sequence in a background thread."""
    import time
    def _chirp():
        beeps = [
            (1200, 80),
            (800, 120),
            (1600, 60),
            (1000, 100),
            (1400, 150),
        ]
        for freq, dur in beeps:
            winsound.Beep(freq, dur)
            time.sleep(0.05)
    threading.Thread(target=_chirp, daemon=True).start()


def win95_raised():
    return (
        f"border-top: 2px solid {W95_BTN_HIGHLIGHT};"
        f"border-left: 2px solid {W95_BTN_HIGHLIGHT};"
        f"border-right: 2px solid {W95_FRAME};"
        f"border-bottom: 2px solid {W95_FRAME};"
    )


def win95_sunken():
    return (
        f"border-top: 2px solid {W95_FRAME};"
        f"border-left: 2px solid {W95_FRAME};"
        f"border-right: 2px solid {W95_BTN_HIGHLIGHT};"
        f"border-bottom: 2px solid {W95_BTN_HIGHLIGHT};"
    )


def win95_btn_style():
    return f"""
        QPushButton {{
            background: {W95_SURFACE};
            color: {W95_TEXT};
            font-family: "{W95_FONT}", Arial, sans-serif;
            font-size: 11px;
            padding: 4px 12px;
            {win95_raised()}
        }}
        QPushButton:hover {{
            background: {W95_BTN_FACE};
        }}
        QPushButton:pressed {{
            {win95_sunken()}
            padding: 5px 11px 3px 13px;
        }}
    """


def log(msg):
    import time
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


# ---------------------------------------------------------------------------
# Notification widget (Win95)
# ---------------------------------------------------------------------------

class PingleNotification(QWidget):
    active = []
    queue = []
    MAX_VISIBLE = 3

    WIDTH = 440
    HEIGHT = 165
    MARGIN = 16
    GAP = 8
    DISPLAY_MS = 30000
    FADE_MS = 500

    def __init__(self, ticket_id, title, action_text, action_color="#000", url=None):
        super().__init__()
        self.ticket_id = ticket_id
        self.url = url or f"{QB_URL}/ticket/{ticket_id}"
        self.slot = None

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        # --- Outer frame ---
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        container = QWidget()
        container.setObjectName("win95frame")
        container.setStyleSheet(f"""
            #win95frame {{
                background: {W95_SURFACE};
                {win95_raised()}
            }}
        """)
        outer_layout.addWidget(container)

        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(3, 3, 3, 3)
        main_layout.setSpacing(0)

        # --- Title bar ---
        titlebar = QWidget()
        titlebar.setFixedHeight(22)

        tb_layout = QHBoxLayout(titlebar)
        tb_layout.setContentsMargins(4, 2, 2, 2)
        tb_layout.setSpacing(4)

        tb_title = QLabel(f"Questboard \u2014 #{ticket_id}")
        tb_title.setFont(QFont(W95_FONT, 9, QFont.Bold))
        tb_title.setStyleSheet("color: #fff; background: transparent;")
        tb_layout.addWidget(tb_title)

        tb_layout.addStretch()

        close_btn = QPushButton("X")
        close_btn.setFixedSize(16, 14)
        close_btn.setCursor(QCursor(Qt.PointingHandCursor))
        close_btn.setFont(QFont(W95_FONT, 7, QFont.Bold))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {W95_SURFACE};
                color: {W95_TEXT};
                {win95_raised()}
                padding: 0px;
                font-size: 8px;
            }}
            QPushButton:pressed {{
                {win95_sunken()}
            }}
        """)
        close_btn.clicked.connect(self.dismiss)
        tb_layout.addWidget(close_btn)

        main_layout.addWidget(titlebar)

        # --- Body ---
        body_frame = QWidget()
        body_frame.setStyleSheet(f"background: {W95_SURFACE}; margin: 4px;")

        body_layout = QVBoxLayout(body_frame)
        body_layout.setContentsMargins(8, 6, 8, 4)
        body_layout.setSpacing(4)

        heading = QLabel(f"#{ticket_id} \u2014 {action_text}")
        heading.setFont(QFont(W95_FONT, 11, QFont.Bold))
        heading.setStyleSheet(f"color: {W95_TEXT}; background: transparent;")
        body_layout.addWidget(heading)

        body = QLabel(title)
        body.setFont(QFont(W95_FONT, 10))
        body.setStyleSheet(f"color: {W95_TEXT}; background: transparent;")
        body.setWordWrap(True)
        body_layout.addWidget(body)

        body_layout.addStretch()

        main_layout.addWidget(body_frame, 1)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(4, 0, 4, 4)
        btn_row.setSpacing(6)
        btn_row.addStretch()

        for label, handler in [("Open Ticket", self.open_ticket), ("Dismiss", self.dismiss)]:
            btn = QPushButton(label)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.setFixedSize(100, 23)
            btn.setFont(QFont(W95_FONT, 9))
            btn.setStyleSheet(win95_btn_style())
            btn.clicked.connect(handler)
            btn_row.addWidget(btn)

        btn_row.addStretch()
        main_layout.addLayout(btn_row)

        # Opacity
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity_effect)

        # Auto-dismiss
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.fade_out)
        self.dismiss_timer.start(self.DISPLAY_MS)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        gradient = QLinearGradient(3, 3, self.width() - 3, 3)
        gradient.setColorAt(0, QColor(W95_TITLE_BLUE))
        gradient.setColorAt(1, QColor(W95_TITLE_BLUE_LIGHT))
        painter.fillRect(3, 3, self.width() - 6, 22, gradient)
        painter.end()

    def show_in_slot(self, slot):
        self.slot = slot
        # Find the screen the cursor is on — notifications appear where you're working
        cursor_screen = QApplication.screenAt(QCursor.pos())
        if cursor_screen is None:
            cursor_screen = QApplication.primaryScreen()
        screen = cursor_screen.availableGeometry()
        x = screen.right() - self.WIDTH - self.MARGIN
        y = screen.top() + self.MARGIN + slot * (self.HEIGHT + self.GAP)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        droid_chirp()

    def fade_out(self):
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(self.FADE_MS)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.OutQuad)
        self.anim.finished.connect(self.dismiss)
        self.anim.start()

    def dismiss(self):
        self.dismiss_timer.stop()
        if self in PingleNotification.active:
            PingleNotification.active.remove(self)
            self._reflow()
            self._process_queue()
        self.close()
        self.deleteLater()

    def open_ticket(self):
        webbrowser.open(self.url, new=0)
        self.dismiss()

    @classmethod
    def send(cls, ticket_id, title, action_text, action_color="#000"):
        notif = cls(ticket_id, title, action_text, action_color)
        if len(cls.active) < cls.MAX_VISIBLE:
            slot = len(cls.active)
            cls.active.append(notif)
            notif.show_in_slot(slot)
        else:
            cls.queue.append(notif)

    @classmethod
    def _reflow(cls):
        for i, notif in enumerate(cls.active):
            notif.show_in_slot(i)

    @classmethod
    def _process_queue(cls):
        while cls.queue and len(cls.active) < cls.MAX_VISIBLE:
            notif = cls.queue.pop(0)
            slot = len(cls.active)
            cls.active.append(notif)
            notif.show_in_slot(slot)


# ---------------------------------------------------------------------------
# DB watcher
# ---------------------------------------------------------------------------

def api_get(path):
    """Fetch JSON from the Questboard API."""
    try:
        resp = urllib.request.urlopen(f"{QB_API}{path}", timeout=5)
        return json.loads(resp.read().decode())
    except Exception:
        return None


# Track seen ticket IDs to avoid duplicate notifications
_seen_blocked = set()


def classify_event(action, detail):
    if action == "created":
        return "New ticket", "#7F9D9D"
    elif action == "status":
        if detail and "->" in detail:
            new_status = detail.split("->")[-1].strip()
            if new_status in ("done", "n/a"):
                return "Completed", "#7F9D9D"
            elif new_status == "blocked":
                return "Blocked", "#a05a3a"
            else:
                return f"Status: {new_status}", "#B0AD92"
    return "Updated", "#B0AD92"


class PingleWatcher:
    def __init__(self, app, once=False):
        self.app = app
        self.once = once
        # Seed seen set with currently blocked tickets so we don't fire on startup
        tickets = api_get("/api/tickets?project=pings&status=blocked") or []
        for t in tickets:
            _seen_blocked.add(t["id"])
        log(f"Watcher started. {len(_seen_blocked)} existing blocked tickets.")

        if not once:
            self.timer = QTimer()
            self.timer.timeout.connect(self.poll)
            self.timer.start(POLL_MS)

        QTimer.singleShot(500, self.poll)

    def poll(self):
        try:
            tickets = api_get("/api/tickets?project=pings&status=blocked")
            if tickets is None:
                return

            for t in tickets:
                if t["id"] not in _seen_blocked:
                    _seen_blocked.add(t["id"])
                    action_text = "Blocked"
                    action_color = "#a05a3a"
                    log(f"Ping: #{t['id']} {t['title']} [{action_text}]")
                    PingleNotification.send(t["id"], t["title"], action_text, action_color)

        except Exception as e:
            log(f"Poll error: {e}")

        if self.once:
            QTimer.singleShot(35000, self.app.quit)


# ---------------------------------------------------------------------------
# Lockfile
# ---------------------------------------------------------------------------

def check_lock():
    if os.path.exists(LOCK_PATH):
        try:
            with open(LOCK_PATH) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return True
        except (ValueError, OSError, ProcessLookupError):
            os.remove(LOCK_PATH)
    return False


def write_lock():
    with open(LOCK_PATH, "w") as f:
        f.write(str(os.getpid()))


def remove_lock():
    try:
        os.remove(LOCK_PATH)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import atexit

    once = "--once" in sys.argv

    if not once and check_lock():
        print("Pingle is already running.")
        sys.exit(1)

    app = QApplication(sys.argv)

    if not once:
        write_lock()
        atexit.register(remove_lock)

    watcher = PingleWatcher(app, once=once)

    if not once:
        print(f"Pingle running. Watching /pings board... (PID {os.getpid()})")

    sys.exit(app.exec_())
