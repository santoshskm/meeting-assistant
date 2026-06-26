from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


def _circle_icon(hex_color: str, size: int = 22) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(hex_color))
    p.setPen(Qt.PenStyle.NoPen)
    m = 3
    p.drawEllipse(m, m, size - 2 * m, size - 2 * m)
    p.end()
    return QIcon(pix)


class SystemTray(QSystemTrayIcon):
    show_window = pyqtSignal()
    quit_app = pyqtSignal()

    def __init__(self, parent=None):
        # Icons must be created after QApplication exists, not at module level
        self._icon_idle = _circle_icon("#6b7280")
        self._icon_detected = _circle_icon("#22c55e")
        self._icon_recording = _circle_icon("#ef4444")
        super().__init__(self._icon_idle, parent)
        self.setToolTip("Meeting Assistant — Idle")
        self._build_menu()
        self.activated.connect(self._on_activated)

    # --- public ---

    def set_idle(self):
        self.setIcon(self._icon_idle)
        self.setToolTip("Meeting Assistant — Idle")
        self._status_action.setText("Idle — no meeting detected")

    def set_detected(self, app_name: str):
        self.setIcon(self._icon_detected)
        self.setToolTip(f"Meeting Assistant — {app_name} detected")
        self._status_action.setText(f"{app_name} detected")
        self.showMessage(
            "Meeting Detected",
            f"{app_name} is running. Recording started automatically.",
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    def set_recording(self, app_name: str):
        self.setIcon(self._icon_recording)
        self.setToolTip(f"Meeting Assistant — Recording ({app_name})")
        self._status_action.setText(f"Recording — {app_name}")

    # --- internal ---

    def _build_menu(self):
        menu = QMenu()

        self._status_action = menu.addAction("Idle — no meeting detected")
        self._status_action.setEnabled(False)

        menu.addSeparator()
        open_action = menu.addAction("Open Meeting Assistant")
        open_action.triggered.connect(self.show_window.emit)

        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_app.emit)

        self.setContextMenu(menu)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window.emit()
