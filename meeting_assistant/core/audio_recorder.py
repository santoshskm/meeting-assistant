from __future__ import annotations

import threading
import time
from queue import Empty, Queue

import sounddevice as sd
from PyQt6.QtCore import QObject, pyqtSignal

from core.speaker_segmenter import SpeakerSegmenter

SAMPLE_RATE = 16_000
CHANNELS = 1


class AudioRecorder(QObject):
    audio_chunk_ready = pyqtSignal(str, float, str)  # (wav_path, start_ts, speaker_id)
    recording_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._recording = False
        self._stream: sd.InputStream | None = None
        self._frame_queue: Queue = Queue()
        self._process_thread: threading.Thread | None = None
        self._segmenter = SpeakerSegmenter()
        self._segmenter.segment_ready.connect(self._on_segment_ready)

    # ---------------------------------------------------------------- public

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
        self._segmenter.reset()
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
                target=self._process_frames, daemon=True
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
        if self._process_thread:
            self._process_thread.join(timeout=3.0)
        self._segmenter.flush()

    # --------------------------------------------------------------- private

    def _audio_callback(self, indata, frames, time_info, status):
        if self._recording:
            self._frame_queue.put((indata[:, 0].copy(), time.time()))

    def _process_frames(self):
        while self._recording or not self._frame_queue.empty():
            try:
                block, ts = self._frame_queue.get(timeout=1.0)
                self._segmenter.add_audio(block, ts)
            except Empty:
                continue
            except Exception as exc:
                self.recording_error.emit(str(exc))

    def _on_segment_ready(self, wav_path: str, timestamp: float, speaker_id: str):
        self.audio_chunk_ready.emit(wav_path, timestamp, speaker_id)
