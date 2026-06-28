from __future__ import annotations

import os
import threading
from queue import Empty, Queue

from PyQt6.QtCore import QObject, pyqtSignal

from config import TRANSCRIPTION_LANGUAGE, WHISPER_MODEL

# Languages accepted in auto-detect mode — anything else is a hallucination
_ALLOWED_LANGUAGES = {"en", "hi"}
_MIN_LANGUAGE_PROB = 0.6  # discard if Whisper is less than 60% confident


class Transcriber(QObject):
    transcription_ready = pyqtSignal(str, float, str)  # (text, timestamp, speaker_id)
    transcription_error = pyqtSignal(str)
    model_loading = pyqtSignal()
    model_loaded = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._model = None
        self._running = False
        self._queue: Queue = Queue()
        self._worker: threading.Thread | None = None
        self.language: str | None = TRANSCRIPTION_LANGUAGE  # settable at runtime

    # --- public ---

    def load_model(self):
        self.model_loading.emit()
        threading.Thread(target=self._load_model_thread, daemon=True).start()

    def start(self):
        if self._model is None:
            return
        self._running = True
        self._worker = threading.Thread(target=self._transcription_loop, daemon=True)
        self._worker.start()

    def stop(self):
        self._running = False

    def add_audio(self, wav_path: str, timestamp: float, speaker_id: str):
        self._queue.put((wav_path, timestamp, speaker_id))

    # --- internal ---

    def _load_model_thread(self):
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                WHISPER_MODEL,
                device="cpu",
                compute_type="int8",
            )
            self.model_loaded.emit()
        except Exception as exc:
            self.transcription_error.emit(f"Failed to load Whisper model: {exc}")

    def _transcription_loop(self):
        while self._running:
            try:
                wav_path, timestamp, speaker_id = self._queue.get(timeout=1.0)
                text = self._transcribe(wav_path)
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass
                if text.strip():
                    self.transcription_ready.emit(text.strip(), timestamp, speaker_id)
            except Empty:
                continue
            except Exception as exc:
                self.transcription_error.emit(str(exc))

    def _transcribe(self, wav_path: str) -> str:
        if self._model is None:
            return ""
        segments, info = self._model.transcribe(
            wav_path,
            beam_size=5,
            language=self.language,
            temperature=0,                   # greedy decode — much less hallucination
            condition_on_previous_text=False, # each segment independent, stops compounding errors
            no_speech_threshold=0.6,         # discard frames Whisper thinks aren't speech
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        # In auto-detect mode, reject hallucinations in unexpected languages
        if self.language is None:
            if info.language not in _ALLOWED_LANGUAGES:
                return ""
            if info.language_probability < _MIN_LANGUAGE_PROB:
                return ""
        return " ".join(seg.text for seg in segments)