import os
import tempfile
import threading
import wave
from queue import Empty, Queue

import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QObject, pyqtSignal

SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 30  # seconds


class AudioRecorder(QObject):
    audio_chunk_ready = pyqtSignal(str, float)  # (wav_path, timestamp)
    recording_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._recording = False
        self._stream: sd.InputStream | None = None
        self._buffer: list[float] = []
        self._chunk_size = SAMPLE_RATE * CHUNK_DURATION
        self._chunk_queue: Queue = Queue()
        self._process_thread: threading.Thread | None = None

    # --- public ---

    def get_input_devices(self) -> list[tuple[int, str]]:
        return [
            (i, d["name"])
            for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] > 0
        ]

    def find_blackhole_device(self) -> int | None:
        for i, d in enumerate(sd.query_devices()):
            if "blackhole" in d["name"].lower() and d["max_input_channels"] > 0:
                return i
        return None

    def start_recording(self, device_index: int | None = None):
        if self._recording:
            return
        self._recording = True
        self._buffer = []
        try:
            self._stream = sd.InputStream(
                device=device_index,
                channels=CHANNELS,
                samplerate=SAMPLE_RATE,
                dtype="float32",
                blocksize=1024,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._process_thread = threading.Thread(
                target=self._process_chunks, daemon=True
            )
            self._process_thread.start()
        except Exception as exc:
            self._recording = False
            self.recording_error.emit(str(exc))

    def stop_recording(self):
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        # Flush remaining buffer
        if self._buffer:
            chunk = np.array(self._buffer, dtype=np.float32)
            self._buffer = []
            path = self._save_wav(chunk)
            if path:
                import time
                self.audio_chunk_ready.emit(path, time.time())

    # --- internal ---

    def _audio_callback(self, indata, frames, time_info, status):
        if not self._recording:
            return
        self._buffer.extend(indata[:, 0].tolist())
        if len(self._buffer) >= self._chunk_size:
            chunk = np.array(self._buffer[: self._chunk_size], dtype=np.float32)
            self._buffer = self._buffer[self._chunk_size :]
            import time
            self._chunk_queue.put((chunk, time.time()))

    def _process_chunks(self):
        while self._recording or not self._chunk_queue.empty():
            try:
                chunk, timestamp = self._chunk_queue.get(timeout=1.0)
                path = self._save_wav(chunk)
                if path:
                    self.audio_chunk_ready.emit(path, timestamp)
            except Empty:
                continue
            except Exception as exc:
                self.recording_error.emit(str(exc))

    def _save_wav(self, audio: np.ndarray) -> str | None:
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name
            tmp.close()
            with wave.open(tmp_path, "w") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes((audio * 32767).astype(np.int16).tobytes())
            return tmp_path
        except Exception:
            return None
