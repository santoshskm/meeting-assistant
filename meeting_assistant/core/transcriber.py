import os
import threading
from queue import Empty, Queue

from PyQt6.QtCore import QObject, pyqtSignal

from config import WHISPER_MODEL


class Transcriber(QObject):
    transcription_ready = pyqtSignal(str, float)   # (text, timestamp)
    transcription_error = pyqtSignal(str)
    model_loading = pyqtSignal()
    model_loaded = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._model = None
        self._running = False
        self._queue: Queue = Queue()
        self._worker: threading.Thread | None = None

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

    def add_audio(self, wav_path: str, timestamp: float):
        self._queue.put((wav_path, timestamp))

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
                wav_path, timestamp = self._queue.get(timeout=1.0)
                text = self._transcribe(wav_path)
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass
                if text.strip():
                    self.transcription_ready.emit(text.strip(), timestamp)
            except Empty:
                continue
            except Exception as exc:
                self.transcription_error.emit(str(exc))

    def _transcribe(self, wav_path: str) -> str:
        if self._model is None:
            return ""
        segments, _ = self._model.transcribe(
            wav_path,
            beam_size=5,
            language="en",
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        return " ".join(seg.text for seg in segments)