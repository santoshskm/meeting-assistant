from __future__ import annotations

import time

from PyQt6.QtCore import QDateTime, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.ai_processor import AIProcessor
from core.audio_recorder import AudioRecorder
from core.meeting_detector import MeetingDetector
from core.transcriber import Transcriber
from utils.report_generator import ReportGenerator


_DARK_BG = "#0f172a"
_PANEL_BG = "#1e293b"
_BORDER = "#334155"
_TEXT = "#e2e8f0"
_MUTED = "#64748b"

_SPEAKER_COLORS = ["#60a5fa", "#34d399", "#f97316", "#a78bfa", "#f43f5e", "#facc15"]


class MeetingAssistantWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Meeting Assistant")
        self.setMinimumSize(1100, 720)

        self.meeting_detector = MeetingDetector()
        self.audio_recorder = AudioRecorder()
        self.transcriber = Transcriber()
        self.ai_processor = AIProcessor()
        self.report_generator = ReportGenerator()

        self._transcript_entries: list[tuple[str, str, str]] = []  # (ts, speaker, text)
        self._is_recording = False
        self._recording_start: float | None = None
        self._current_app: str | None = None
        self._auto_record = False

        self._setup_ui()
        self._connect_signals()

        self.meeting_detector.start()
        self.transcriber.load_model()

        self._timer = QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick_duration)

    # ------------------------------------------------------------------ UI ---

    def _setup_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        layout.addWidget(self._make_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._make_transcript_panel())
        splitter.addWidget(self._make_summary_panel())
        splitter.setSizes([620, 480])
        layout.addWidget(splitter, stretch=1)

        layout.addWidget(self._make_controls())

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Loading Whisper model…")

        self.setStyleSheet(f"QMainWindow, QWidget {{ background-color: {_DARK_BG}; color: {_TEXT}; }}")

    def _make_header(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {_PANEL_BG};
                border-radius: 8px;
            }}
        """)
        row = QHBoxLayout(frame)
        row.setContentsMargins(14, 10, 14, 10)

        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color: {_MUTED}; font-size: 20px;")
        row.addWidget(self._dot)

        self._meeting_label = QLabel("No Meeting Detected")
        self._meeting_label.setStyleSheet(f"color: {_MUTED}; font-size: 14px; font-weight: bold;")
        row.addWidget(self._meeting_label)

        row.addStretch()

        self._duration_label = QLabel("00:00:00")
        self._duration_label.setStyleSheet(f"color: {_MUTED}; font-size: 13px; font-family: 'Menlo', 'Monaco', 'Courier New';")
        row.addWidget(self._duration_label)

        row.addSpacing(20)

        self._auto_cb = QCheckBox("Auto-record meetings")
        self._auto_cb.setChecked(False)
        self._auto_cb.setStyleSheet(f"color: {_MUTED};")
        self._auto_cb.stateChanged.connect(lambda s: setattr(self, "_auto_record", bool(s)))
        row.addWidget(self._auto_cb)

        return frame

    def _make_transcript_panel(self) -> QGroupBox:
        box = self._group_box("Live Transcript")
        layout = box.layout()

        self._transcript_view = QTextEdit()
        self._transcript_view.setReadOnly(True)
        self._transcript_view.setPlaceholderText(
            "Transcript will appear here once recording starts…\n\n"
            "Tip: Install BlackHole (free virtual audio driver) to capture\n"
            "full meeting audio including remote participants."
        )
        self._style_text_edit(self._transcript_view)
        layout.addWidget(self._transcript_view)

        row = QHBoxLayout()
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet(self._btn_style(_MUTED))
        clear_btn.clicked.connect(self._clear_transcript)
        row.addWidget(clear_btn)
        row.addStretch()
        self._word_count = QLabel("0 words")
        self._word_count.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
        row.addWidget(self._word_count)
        layout.addLayout(row)

        return box

    def _make_summary_panel(self) -> QGroupBox:
        box = self._group_box("Summary & Action Items")
        layout = box.layout()

        # Model picker
        row = QHBoxLayout()
        lbl = QLabel("Claude model:")
        lbl.setStyleSheet(f"color: {_MUTED};")
        row.addWidget(lbl)
        self._model_combo = QComboBox()
        self._model_combo.setStyleSheet(f"background: {_PANEL_BG}; color: {_TEXT}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 2px 6px;")
        self._refresh_models()
        row.addWidget(self._model_combo, stretch=1)
        layout.addLayout(row)

        self._generate_btn = QPushButton("Generate Summary")
        self._generate_btn.setStyleSheet(self._btn_style("#3b82f6", hover="#2563eb"))
        self._generate_btn.clicked.connect(self._generate_summary)
        layout.addWidget(self._generate_btn)

        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 0)
        self._ai_progress.setMaximumHeight(4)
        self._ai_progress.hide()
        layout.addWidget(self._ai_progress)

        self._summary_view = QTextEdit()
        self._summary_view.setReadOnly(True)
        self._summary_view.setPlaceholderText(
            "Click 'Generate Summary' to produce an AI summary using Claude.\n\n"
            "Requires ANTHROPIC_API_KEY set in your environment."
        )
        self._style_text_edit(self._summary_view)
        layout.addWidget(self._summary_view)

        return box

    def _make_controls(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ background-color: {_PANEL_BG}; border-radius: 8px; }}")
        row = QHBoxLayout(frame)
        row.setContentsMargins(14, 10, 14, 10)

        lbl = QLabel("Audio device:")
        lbl.setStyleSheet(f"color: {_MUTED};")
        row.addWidget(lbl)

        self._device_combo = QComboBox()
        self._device_combo.setMinimumWidth(220)
        self._device_combo.setStyleSheet(f"background: {_DARK_BG}; color: {_TEXT}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 2px 6px;")
        self._populate_devices()
        row.addWidget(self._device_combo)

        row.addSpacing(16)

        lang_lbl = QLabel("Language:")
        lang_lbl.setStyleSheet(f"color: {_MUTED};")
        row.addWidget(lang_lbl)

        self._lang_combo = QComboBox()
        self._lang_combo.setStyleSheet(f"background: {_DARK_BG}; color: {_TEXT}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 2px 6px;")
        self._lang_combo.addItem("English", "en")
        self._lang_combo.addItem("Hindi", "hi")
        self._lang_combo.addItem("Hinglish / Auto", None)
        self._lang_combo.setCurrentIndex(0)
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)
        row.addWidget(self._lang_combo)

        row.addSpacing(16)

        self._record_btn = QPushButton("Start Recording")
        self._record_btn.setStyleSheet(self._btn_style("#22c55e", hover="#16a34a"))
        self._record_btn.clicked.connect(self._toggle_recording)
        row.addWidget(self._record_btn)

        row.addStretch()

        export_md = QPushButton("Export Markdown")
        export_md.setStyleSheet(self._btn_style(_MUTED, hover="#475569", pressed="#334155"))
        export_md.clicked.connect(lambda: self._export("md"))
        row.addWidget(export_md)

        export_pdf = QPushButton("Export PDF")
        export_pdf.setStyleSheet(self._btn_style(_MUTED, hover="#475569", pressed="#334155"))
        export_pdf.clicked.connect(lambda: self._export("pdf"))
        row.addWidget(export_pdf)

        return frame

    # ----------------------------------------------------------- helpers ---

    def _group_box(self, title: str) -> QGroupBox:
        box = QGroupBox(title)
        box.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold; font-size: 13px;
                border: 1px solid {_BORDER}; border-radius: 6px;
                margin-top: 8px; padding-top: 8px; color: {_MUTED};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 12px; padding: 0 4px;
            }}
        """)
        QVBoxLayout(box)
        return box

    def _style_text_edit(self, widget: QTextEdit):
        widget.setStyleSheet(f"""
            QTextEdit {{
                background-color: {_DARK_BG}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 4px;
                font-size: 13px; padding: 8px;
            }}
        """)

    def _btn_style(self, bg: str, hover: str | None = None, pressed: str | None = None) -> str:
        hover_css = f"QPushButton:hover {{ background-color: {hover}; }}" if hover else ""
        _pressed_color = pressed or hover or bg
        pressed_css = f"QPushButton:pressed {{ background-color: {_pressed_color}; border: 2px solid rgba(255,255,255,0.4); padding: 6px 17px; }}"
        return f"""
            QPushButton {{
                background-color: {bg}; color: white; border: none;
                border-radius: 6px; padding: 7px 18px; font-weight: bold;
            }}
            {hover_css}
            {pressed_css}
            QPushButton:disabled {{ opacity: 0.5; }}
        """

    # ---------------------------------------------------------- signals ---

    def _connect_signals(self):
        self.meeting_detector.meeting_started.connect(self._on_meeting_started)
        self.meeting_detector.meeting_ended.connect(self._on_meeting_ended)

        self.audio_recorder.audio_chunk_ready.connect(self._on_audio_chunk)
        self.audio_recorder.recording_error.connect(
            lambda e: self._status_bar.showMessage(f"Recording error: {e}")
        )

        self.transcriber.model_loading.connect(
            lambda: self._status_bar.showMessage("Loading Whisper model…")
        )
        self.transcriber.model_loaded.connect(self._on_model_loaded)
        self.transcriber.transcription_ready.connect(self._on_transcription)
        self.transcriber.transcription_error.connect(
            lambda e: self._status_bar.showMessage(f"Transcription error: {e}")
        )

        self.ai_processor.processing_started.connect(self._on_ai_started)
        self.ai_processor.summary_ready.connect(self._on_summary_ready)
        self.ai_processor.processing_error.connect(self._on_ai_error)

    # ------------------------------------------------------- event slots ---

    def _on_meeting_started(self, app: str):
        self._current_app = app
        self._dot.setStyleSheet("color: #22c55e; font-size: 20px;")
        self._meeting_label.setText(f"{app} — Meeting Detected")
        self._meeting_label.setStyleSheet("color: #22c55e; font-size: 14px; font-weight: bold;")
        self._status_bar.showMessage(f"{app} detected")
        if self._auto_record and not self._is_recording:
            self._start_recording()

    def _on_meeting_ended(self, app: str):
        self._current_app = None
        self._dot.setStyleSheet(f"color: {_MUTED}; font-size: 20px;")
        self._meeting_label.setText("No Meeting Detected")
        self._meeting_label.setStyleSheet(f"color: {_MUTED}; font-size: 14px; font-weight: bold;")
        self._status_bar.showMessage(f"{app} ended")
        if self._is_recording:
            self._stop_recording()

    def _on_audio_chunk(self, wav_path: str, timestamp: float, speaker_id: str):
        self.transcriber.add_audio(wav_path, timestamp, speaker_id)

    def _on_transcription(self, text: str, timestamp: float, speaker_id: str):
        ts = QDateTime.fromSecsSinceEpoch(int(timestamp)).toString("hh:mm:ss")
        self._transcript_entries.append((ts, speaker_id, text))

        # pick a stable color per speaker number
        try:
            idx = int(speaker_id.split()[-1]) - 1
        except (ValueError, IndexError):
            idx = 0
        color = _SPEAKER_COLORS[idx % len(_SPEAKER_COLORS)]

        cursor = self._transcript_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(
            f'<span style="color:{color}; font-size:12px; font-weight:bold;">{speaker_id}</span>'
            f'<span style="color:{_MUTED}; font-size:11px;"> [{ts}]</span><br/>'
            f'<span style="color:{_TEXT};">{text}</span><br/><br/>'
        )
        self._transcript_view.setTextCursor(cursor)
        self._transcript_view.ensureCursorVisible()

        all_text = " ".join(t for _, _, t in self._transcript_entries)
        self._word_count.setText(f"{len(all_text.split())} words")

    def _on_model_loaded(self):
        self._status_bar.showMessage("Whisper model loaded — ready")
        self.transcriber.start()

    def _on_ai_started(self):
        self._generate_btn.setEnabled(False)
        self._generate_btn.setText("Generating…")
        self._ai_progress.show()

    def _on_summary_ready(self, text: str):
        self._generate_btn.setEnabled(True)
        self._generate_btn.setText("Generate Summary")
        self._ai_progress.hide()
        self._summary_view.setMarkdown(text)
        self._status_bar.showMessage("Summary generated")

    def _on_ai_error(self, msg: str):
        self._generate_btn.setEnabled(True)
        self._generate_btn.setText("Generate Summary")
        self._ai_progress.hide()
        self._status_bar.showMessage("Summary failed — see dialog")
        QMessageBox.warning(self, "Summary Error", msg)

    # ---------------------------------------------------------- actions ---

    def _toggle_recording(self):
        if self._is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        device = self._device_combo.currentData()
        self.audio_recorder.start_recording(device)
        self._is_recording = True
        self._recording_start = time.time()
        self._timer.start()
        self._record_btn.setText("Stop Recording")
        self._record_btn.setStyleSheet(self._btn_style("#ef4444", hover="#dc2626"))
        self._status_bar.showMessage("Recording…")

    def _stop_recording(self):
        self.audio_recorder.stop_recording()
        self._is_recording = False
        self._timer.stop()
        self._record_btn.setText("Start Recording")
        self._record_btn.setStyleSheet(self._btn_style("#22c55e", hover="#16a34a"))
        self._status_bar.showMessage("Recording stopped")

    def _tick_duration(self):
        if self._recording_start:
            s = int(time.time() - self._recording_start)
            self._duration_label.setText(f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}")

    def _clear_transcript(self):
        self._transcript_view.clear()
        self._transcript_entries.clear()
        self._word_count.setText("0 words")

    def _generate_summary(self):
        if not self._transcript_entries:
            QMessageBox.information(self, "Empty Transcript", "Nothing to summarize yet.")
            return
        model = self._model_combo.currentText()
        if model:
            self.ai_processor.model = model
        full = "\n".join(f"[{ts}] {spk}: {txt}" for ts, spk, txt in self._transcript_entries)
        self.ai_processor.generate_summary(full)

    def _export(self, fmt: str):
        if not self._transcript_entries:
            QMessageBox.information(self, "Nothing to Export", "Record a meeting first.")
            return
        transcript = "\n".join(f"[{ts}] {spk}: {txt}" for ts, spk, txt in self._transcript_entries)
        summary = self._summary_view.toMarkdown()
        path = self.report_generator.save(
            transcript=transcript,
            summary=summary,
            app_name=self._current_app or "Unknown",
            fmt=fmt,
        )
        self._status_bar.showMessage(f"Saved: {path}")
        fmt_label = "Markdown" if fmt == "md" else "PDF"
        QMessageBox.information(
            self,
            f"{fmt_label} Exported Successfully",
            f"Your meeting report has been saved to:\n\n{path}",
        )

    def _on_language_changed(self, _index: int):
        self.transcriber.language = self._lang_combo.currentData()

    def _populate_devices(self):
        self._device_combo.clear()
        self._device_combo.addItem("Default Microphone", None)
        bh = self.audio_recorder.find_blackhole_device()
        if bh is not None:
            self._device_combo.insertItem(1, "BlackHole (System Audio — recommended)", bh)
            self._device_combo.setCurrentIndex(1)
        for idx, name in self.audio_recorder.get_input_devices():
            if "blackhole" not in name.lower():
                self._device_combo.addItem(name, idx)

    def _refresh_models(self):
        self._model_combo.clear()
        for m in self.ai_processor.get_available_models():
            self._model_combo.addItem(m)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
