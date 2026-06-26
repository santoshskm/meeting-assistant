import threading
import time

import psutil
from PyQt6.QtCore import QObject, pyqtSignal

from config import MEETING_PROCESSES, MEETING_CHECK_INTERVAL


class MeetingDetector(QObject):
    meeting_started = pyqtSignal(str)   # emits app name
    meeting_ended = pyqtSignal(str)     # emits app name

    def __init__(self):
        super().__init__()
        self._running = False
        self._current_meetings: set[str] = set()
        self._thread: threading.Thread | None = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    @property
    def active_meetings(self) -> set[str]:
        return self._current_meetings.copy()

    # --- internal ---

    def _monitor_loop(self):
        while self._running:
            detected = self._detect_meetings()

            for app in detected - self._current_meetings:
                self.meeting_started.emit(app)

            for app in self._current_meetings - detected:
                self.meeting_ended.emit(app)

            self._current_meetings = detected
            time.sleep(MEETING_CHECK_INTERVAL)

    def _detect_meetings(self) -> set[str]:
        try:
            running = {p.name() for p in psutil.process_iter(["name"])}
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return self._current_meetings.copy()

        detected: set[str] = set()
        for app_name, proc_names in MEETING_PROCESSES.items():
            for proc in proc_names:
                if any(proc.lower() in r.lower() for r in running):
                    detected.add(app_name)
                    break
        return detected
