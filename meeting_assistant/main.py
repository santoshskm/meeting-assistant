"""
Meeting Assistant — entry point.

Run:
    python meeting_assistant/main.py
"""
import os
import sys

# Ensure the package root is on the path regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication

from ui.main_window import MeetingAssistantWindow
from ui.system_tray import SystemTray


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Meeting Assistant")
    app.setQuitOnLastWindowClosed(False)   # keep alive in system tray

    app.setStyle("Fusion")

    window = MeetingAssistantWindow()
    window.show()

    tray = SystemTray()
    tray.show()

    # Wire tray ↔ window
    tray.show_window.connect(window.show)
    tray.show_window.connect(window.raise_)
    tray.quit_app.connect(app.quit)

    # Mirror meeting state to tray icon
    window.meeting_detector.meeting_started.connect(tray.set_detected)
    window.meeting_detector.meeting_ended.connect(lambda _: tray.set_idle())

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
