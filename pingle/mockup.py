"""
Pingle mockup — PyQt5 notification popup for design review.
Fires a single dummy notification in the top-right corner.
"""

import sys
import webbrowser
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QHBoxLayout, QVBoxLayout, QGraphicsOpacityEffect,
)
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PyQt5.QtGui import QFont, QColor, QCursor


class PingleNotification(QWidget):
    """A single notification popup."""

    # Class-level tracking for stacking
    active = []
    queue = []
    MAX_VISIBLE = 3

    WIDTH = 640
    HEIGHT = 180
    MARGIN = 16
    GAP = 8
    DISPLAY_MS = 30000
    FADE_MS = 500

    def __init__(self, ticket_id, title, action, detail="", url=None):
        super().__init__()
        self.ticket_id = ticket_id
        self.url = url or f"http://localhost:5151/ticket/{ticket_id}"
        self.slot = None

        # Window flags: frameless, always on top, tool window (no taskbar entry)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        # Build action label
        if action == "created":
            action_text = "New ticket"
            action_color = "#7F9D9D"
        elif detail and "-> done" in detail:
            action_text = "Completed"
            action_color = "#7F9D9D"
        elif detail and "-> blocked" in detail:
            action_text = "Blocked"
            action_color = "#a05a3a"
        elif detail and "->" in detail:
            new_status = detail.split("->")[-1].strip()
            action_text = f"Status: {new_status}"
            action_color = "#B0AD92"
        else:
            action_text = "Updated"
            action_color = "#B0AD92"

        # --- Layout ---
        container = QWidget(self)
        container.setGeometry(0, 0, self.WIDTH, self.HEIGHT)
        container.setStyleSheet("""
            QWidget {
                background-color: #231e18;
                border: 1px solid #3a3228;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 10, 10, 10)
        layout.setSpacing(4)

        # Top row: #id — action | x
        top_row = QHBoxLayout()
        top_row.setSpacing(0)

        id_label = QLabel(f"#{ticket_id}")
        id_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        id_label.setStyleSheet("color: #CDA473; border: none; background: transparent;")
        top_row.addWidget(id_label)

        dash = QLabel(" — ")
        dash.setFont(QFont("Segoe UI", 9))
        dash.setStyleSheet("color: #b0a898; border: none; background: transparent;")
        top_row.addWidget(dash)

        action_label = QLabel(action_text)
        action_label.setFont(QFont("Segoe UI", 9))
        action_label.setStyleSheet(f"color: {action_color}; border: none; background: transparent;")
        top_row.addWidget(action_label)

        top_row.addStretch()

        close_btn = QPushButton("x")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(QCursor(Qt.PointingHandCursor))
        close_btn.setStyleSheet("""
            QPushButton {
                color: #b0a898;
                background: transparent;
                border: none;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #e8e0d4;
            }
        """)
        close_btn.clicked.connect(self.dismiss)
        top_row.addWidget(close_btn)

        layout.addLayout(top_row)

        # Title
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 11))
        title_label.setStyleSheet("color: #e8e0d4; border: none; background: transparent;")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        # Bottom row: board name | open link
        bottom_row = QHBoxLayout()

        board_label = QLabel("pings")
        board_label.setFont(QFont("Segoe UI", 8))
        board_label.setStyleSheet("color: #665841; border: none; background: transparent;")
        bottom_row.addWidget(board_label)

        bottom_row.addStretch()

        link = QPushButton("Open ticket")
        link.setCursor(QCursor(Qt.PointingHandCursor))
        link.setStyleSheet("""
            QPushButton {
                color: #B0AD92;
                background: transparent;
                border: none;
                font-size: 9pt;
                text-decoration: underline;
            }
            QPushButton:hover {
                color: #e8e0d4;
            }
        """)
        link.clicked.connect(self.open_ticket)
        bottom_row.addWidget(link)

        layout.addLayout(bottom_row)

        # Opacity effect for fade-out
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity_effect)

        # Auto-dismiss timer
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.fade_out)
        self.dismiss_timer.start(self.DISPLAY_MS)

    def show_in_slot(self, slot):
        self.slot = slot
        screen = QApplication.primaryScreen().geometry()
        x = screen.right() - self.WIDTH - self.MARGIN
        y = screen.top() + self.MARGIN + slot * (self.HEIGHT + self.GAP)
        self.move(x, y)
        self.show()

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
    def send(cls, ticket_id, title, action, detail="", url=None):
        notif = cls(ticket_id, title, action, detail, url)
        if len(cls.active) < cls.MAX_VISIBLE:
            slot = len(cls.active)
            cls.active.append(notif)
            notif.show_in_slot(slot)
        else:
            cls.queue.append(notif)

    @classmethod
    def _reflow(cls):
        """Reposition all active notifications to close gaps."""
        for i, notif in enumerate(cls.active):
            notif.show_in_slot(i)

    @classmethod
    def _process_queue(cls):
        """Promote queued notifications to active slots."""
        while cls.queue and len(cls.active) < cls.MAX_VISIBLE:
            notif = cls.queue.pop(0)
            slot = len(cls.active)
            cls.active.append(notif)
            notif.show_in_slot(slot)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Fire a single mock notification
    PingleNotification.send(
        ticket_id=222,
        title="Zug Zug! Job Done!",
        action="created",
    )

    sys.exit(app.exec_())
