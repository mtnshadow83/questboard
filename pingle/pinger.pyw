"""
Pinger — desktop button that fires Pingle notifications on click.
Win95 styled.
"""

import sys
import webbrowser
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QHBoxLayout, QVBoxLayout, QGraphicsOpacityEffect,
    QSizePolicy, QFrame,
)
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QCursor, QLinearGradient, QPalette, QColor, QPainter

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


def win95_raised():
    """Box shadow emulation for raised Win95 border."""
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

    def __init__(self, ticket_id, title, action, detail="", url=None):
        super().__init__()
        self.ticket_id = ticket_id
        self.url = url or f"http://localhost:5151/ticket/{ticket_id}"
        self.slot = None

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.resize(self.WIDTH, self.HEIGHT)
        self.setMinimumSize(200, 80)
        self._resize_edge = None
        self._resize_origin = None
        self._resize_geo = None
        self.setMouseTracking(True)
        self.EDGE = 8

        # Action text
        if action == "created":
            action_text = "New ticket"
        elif detail and "-> done" in detail:
            action_text = "Completed"
        elif detail and "-> blocked" in detail:
            action_text = "Blocked"
        elif detail and "->" in detail:
            action_text = f"Status: {detail.split('->')[-1].strip()}"
        else:
            action_text = "Updated"

        # --- Outer frame (Win95 raised border) ---
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

        # --- Title bar (gradient blue) ---
        titlebar = QWidget()
        titlebar.setFixedHeight(22)
        titlebar.setObjectName("titlebar")

        tb_layout = QHBoxLayout(titlebar)
        tb_layout.setContentsMargins(4, 2, 2, 2)
        tb_layout.setSpacing(4)

        tb_title = QLabel(f"Questboard — #{ticket_id}")
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

        # --- Body area (sunken field) ---
        body_frame = QWidget()
        body_frame.setObjectName("bodyframe")
        body_frame.setStyleSheet(f"""
            #bodyframe {{
                background: {W95_SURFACE};
                margin: 4px;
            }}
        """)

        body_layout = QVBoxLayout(body_frame)
        body_layout.setContentsMargins(8, 6, 8, 4)
        body_layout.setSpacing(4)

        heading = QLabel(f"#{ticket_id} — {action_text}")
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

        # --- Button row ---
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(4, 0, 4, 4)
        btn_row.setSpacing(6)
        btn_row.addStretch()

        open_btn = QPushButton("Open Ticket")
        open_btn.setCursor(QCursor(Qt.PointingHandCursor))
        open_btn.setFixedSize(100, 23)
        open_btn.setFont(QFont(W95_FONT, 9))
        open_btn.setStyleSheet(win95_btn_style())
        open_btn.clicked.connect(self.open_ticket)
        btn_row.addWidget(open_btn)

        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.setCursor(QCursor(Qt.PointingHandCursor))
        dismiss_btn.setFixedSize(100, 23)
        dismiss_btn.setFont(QFont(W95_FONT, 9))
        dismiss_btn.setStyleSheet(win95_btn_style())
        dismiss_btn.clicked.connect(self.dismiss)
        btn_row.addWidget(dismiss_btn)

        btn_row.addStretch()

        main_layout.addLayout(btn_row)

        # Opacity for fade
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity_effect)

        # Auto-dismiss
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.fade_out)
        self.dismiss_timer.start(self.DISPLAY_MS)

    def paintEvent(self, event):
        """Paint the titlebar gradient."""
        super().paintEvent(event)
        painter = QPainter(self)
        # Titlebar gradient: starts at y=3 (inside border), height 22
        gradient = QLinearGradient(3, 3, self.width() - 3, 3)
        gradient.setColorAt(0, QColor(W95_TITLE_BLUE))
        gradient.setColorAt(1, QColor(W95_TITLE_BLUE_LIGHT))
        painter.fillRect(3, 3, self.width() - 6, 22, gradient)
        painter.end()

    def show_in_slot(self, slot):
        self.slot = slot
        screen = QApplication.primaryScreen().geometry()
        x = screen.right() - self.width() - self.MARGIN
        y = screen.top() + self.MARGIN + slot * (self.height() + self.GAP)
        self.move(x, y)
        self.show()
        self.raise_()

    def _hit_edge(self, pos):
        e = self.EDGE
        w, h = self.width(), self.height()
        edges = ""
        if pos.y() < e: edges += "t"
        if pos.y() > h - e: edges += "b"
        if pos.x() < e: edges += "l"
        if pos.x() > w - e: edges += "r"
        return edges

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            edges = self._hit_edge(event.pos())
            if edges:
                self._resize_edge = edges
                self._resize_origin = event.globalPos()
                self._resize_geo = self.geometry()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_edge and self._resize_origin:
            delta = event.globalPos() - self._resize_origin
            geo = self._resize_geo
            x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
            if "r" in self._resize_edge:
                w = max(self.minimumWidth(), geo.width() + delta.x())
            if "b" in self._resize_edge:
                h = max(self.minimumHeight(), geo.height() + delta.y())
            if "l" in self._resize_edge:
                dx = min(delta.x(), geo.width() - self.minimumWidth())
                x = geo.x() + dx
                w = geo.width() - dx
            if "t" in self._resize_edge:
                dy = min(delta.y(), geo.height() - self.minimumHeight())
                y = geo.y() + dy
                h = geo.height() - dy
            self.setGeometry(x, y, w, h)
            event.accept()
            return
        edges = self._hit_edge(event.pos())
        if edges in ("l", "r"):
            self.setCursor(Qt.SizeHorCursor)
        elif edges in ("t", "b"):
            self.setCursor(Qt.SizeVerCursor)
        elif edges in ("tl", "br"):
            self.setCursor(Qt.SizeFDiagCursor)
        elif edges in ("tr", "bl"):
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resize_edge = None
        self._resize_origin = None
        self._resize_geo = None
        super().mouseReleaseEvent(event)

    def fade_out(self):
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(self.FADE_MS)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.OutQuad)
        self.anim.finished.connect(self.dismiss)
        self.anim.start()

    def closeEvent(self, event):
        import os
        log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "size.log")
        with open(log, "w") as f:
            f.write(f"WIDTH = {self.width()}\nHEIGHT = {self.height()}\n")
        super().closeEvent(event)

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
        for i, notif in enumerate(cls.active):
            notif.show_in_slot(i)

    @classmethod
    def _process_queue(cls):
        while cls.queue and len(cls.active) < cls.MAX_VISIBLE:
            notif = cls.queue.pop(0)
            slot = len(cls.active)
            cls.active.append(notif)
            notif.show_in_slot(slot)


class PingerButton(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pinger")
        self.setFixedSize(100, 30)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.setStyleSheet(f"background: {W95_SURFACE};")
        self.counter = 230

        btn = QPushButton("Ping!", self)
        btn.setGeometry(0, 0, 100, 30)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setFont(QFont(W95_FONT, 11, QFont.Bold))
        btn.setStyleSheet(win95_btn_style())
        btn.clicked.connect(self.fire)

    def fire(self):
        self.counter += 1
        PingleNotification.send(
            ticket_id=self.counter,
            title="Zug Zug! Job Done!",
            action="created",
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pinger = PingerButton()
    pinger.show()
    sys.exit(app.exec_())
