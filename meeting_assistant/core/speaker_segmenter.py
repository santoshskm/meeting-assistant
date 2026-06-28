from __future__ import annotations

import tempfile
import wave

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

SAMPLE_RATE = 16_000
FRAME_SIZE = 320          # 20 ms at 16 kHz
SILENCE_LIMIT = 40        # 40 × 20 ms = 800 ms silence → end of utterance
MAX_SEGMENT_FRAMES = 1500  # 30 s hard ceiling per segment
MIN_SPEECH_FRAMES = 8     # 160 ms minimum to be a valid utterance
N_BANDS = 40

# Speaker ID thresholds
MATCH_THRESHOLD = 0.87    # cosine sim ≥ this → same speaker
CENTROID_UPDATE_THRESHOLD = 0.92  # only update centroid on high-confidence matches


class SpeakerSegmenter(QObject):
    """VAD + speaker clustering.

    Segments audio at silence boundaries, fingerprints each utterance with
    log mel filterbank features + pitch, and clusters into consistent speaker
    IDs using cosine-similarity matching against running speaker centroids.
    """

    segment_ready = pyqtSignal(str, float, str)  # (wav_path, start_ts, speaker_id)

    def __init__(self):
        super().__init__()
        self._buf: list[float] = []
        self._speech: list[np.ndarray] = []
        self._silence_count = 0
        self._in_speech = False
        self._seg_start: float = 0.0
        self._profiles: list[np.ndarray] = []
        self._energy_window: list[float] = []
        self._threshold = 0.005

    # ---------------------------------------------------------------- public

    def add_audio(self, samples: np.ndarray, block_time: float) -> None:
        self._buf.extend(samples.tolist())
        while len(self._buf) >= FRAME_SIZE:
            frame = np.array(self._buf[:FRAME_SIZE], dtype=np.float32)
            del self._buf[:FRAME_SIZE]
            self._process_frame(frame, block_time)

    def flush(self) -> None:
        if self._in_speech and len(self._speech) >= MIN_SPEECH_FRAMES:
            self._emit_segment(self._seg_start)
        self._in_speech = False
        self._speech.clear()
        self._silence_count = 0

    def reset(self) -> None:
        self._buf.clear()
        self._speech.clear()
        self._silence_count = 0
        self._in_speech = False
        self._profiles.clear()
        self._energy_window.clear()
        self._threshold = 0.005

    # --------------------------------------------------------------- private

    def _update_threshold(self, energy: float) -> None:
        self._energy_window.append(energy)
        if len(self._energy_window) > 200:
            del self._energy_window[0]
        if len(self._energy_window) >= 20:
            s = sorted(self._energy_window)
            self._threshold = max(s[int(len(s) * 0.25)] * 4, 0.003)

    def _process_frame(self, frame: np.ndarray, block_time: float) -> None:
        energy = float(np.sqrt(np.mean(frame ** 2)))
        self._update_threshold(energy)
        is_speech = energy > self._threshold

        if is_speech:
            if not self._in_speech:
                self._in_speech = True
                self._seg_start = block_time
                self._speech.clear()
                self._silence_count = 0
            self._speech.append(frame)
            self._silence_count = 0
            if len(self._speech) >= MAX_SEGMENT_FRAMES:
                self._emit_segment(self._seg_start)
                self._seg_start = block_time
                self._speech.clear()
        else:
            if self._in_speech:
                self._speech.append(frame)
                self._silence_count += 1
                if self._silence_count >= SILENCE_LIMIT:
                    if len(self._speech) >= MIN_SPEECH_FRAMES:
                        self._emit_segment(self._seg_start)
                    self._in_speech = False
                    self._speech.clear()
                    self._silence_count = 0

    def _emit_segment(self, start_ts: float) -> None:
        audio = np.concatenate(self._speech)
        speaker = self._identify_speaker(audio)
        wav_path = self._save_wav(audio)
        if wav_path:
            self.segment_ready.emit(wav_path, start_ts, speaker)

    # ------------------------------------------ feature extraction

    def _extract_features(self, audio: np.ndarray) -> np.ndarray:
        """Log mel filterbank (40 bands) + normalized pitch → speaker fingerprint."""
        n_fft = 512
        hop = 160  # 10 ms hop
        hann = np.hanning(n_fft)

        # Power spectrum average over all frames
        specs = []
        for i in range(0, len(audio) - n_fft, hop):
            spec = np.abs(np.fft.rfft(audio[i: i + n_fft] * hann)) ** 2
            specs.append(spec)
        if not specs:
            return np.zeros(N_BANDS + 1)
        avg_power = np.mean(specs, axis=0)
        n_freqs = len(avg_power)

        # Mel filterbank
        low_mel = 0.0
        high_mel = 2595.0 * np.log10(1.0 + (SAMPLE_RATE / 2.0) / 700.0)
        mel_pts = np.linspace(low_mel, high_mel, N_BANDS + 2)
        hz_pts = 700.0 * (10.0 ** (mel_pts / 2595.0) - 1.0)
        bins = np.clip(
            np.floor((n_fft + 1) * hz_pts / SAMPLE_RATE).astype(int),
            0, n_freqs - 1,
        )
        mel_energy = np.zeros(N_BANDS)
        for m in range(N_BANDS):
            lo, mid, hi = bins[m], bins[m + 1], bins[m + 2]
            if mid > lo:
                w = np.linspace(0.0, 1.0, mid - lo, endpoint=False)
                mel_energy[m] += float(np.dot(avg_power[lo:mid], w))
            if hi > mid:
                w = np.linspace(1.0, 0.0, hi - mid, endpoint=False)
                mel_energy[m] += float(np.dot(avg_power[mid:hi], w))
        log_mel = np.log(mel_energy + 1e-8)

        # Pitch (F0)
        f0_norm = self._estimate_pitch(audio)

        feats = np.append(log_mel, f0_norm).astype(np.float32)
        feats -= feats.mean()
        norm = np.linalg.norm(feats)
        return feats / norm if norm > 0 else feats

    def _estimate_pitch(self, audio: np.ndarray) -> float:
        """Normalized F0 in [0, 1] via autocorrelation (80–400 Hz range)."""
        segment = audio[len(audio) // 4: 3 * len(audio) // 4]
        if len(segment) < 256:
            return 0.0
        segment = segment - segment.mean()
        n = len(segment)
        fft_val = np.fft.rfft(segment, n=n * 2)
        acf = np.fft.irfft(fft_val * fft_val.conj())[:n]
        if acf[0] == 0:
            return 0.0
        acf /= acf[0]
        min_lag = int(SAMPLE_RATE / 400)   # 400 Hz
        max_lag = min(int(SAMPLE_RATE / 80), n - 1)  # 80 Hz
        if min_lag >= max_lag:
            return 0.0
        peak_lag = min_lag + int(np.argmax(acf[min_lag:max_lag]))
        f0 = SAMPLE_RATE / max(peak_lag, 1)
        return float(np.clip((f0 - 80.0) / 320.0, 0.0, 1.0))

    # ------------------------------------------ speaker identification

    def _identify_speaker(self, audio: np.ndarray) -> str:
        feats = self._extract_features(audio)

        if not self._profiles:
            self._profiles.append(feats.copy())
            return "Speaker 1"

        sims = [float(np.dot(feats, p)) for p in self._profiles]
        best = int(np.argmax(sims))

        if sims[best] >= MATCH_THRESHOLD:
            # Only update centroid on high-confidence matches to prevent drift
            if sims[best] >= CENTROID_UPDATE_THRESHOLD:
                p = 0.9 * self._profiles[best] + 0.1 * feats
                n = np.linalg.norm(p)
                self._profiles[best] = p / n if n > 0 else p
            return f"Speaker {best + 1}"

        self._profiles.append(feats.copy())
        return f"Speaker {len(self._profiles)}"

    # ------------------------------------------ wav I/O

    def _save_wav(self, audio: np.ndarray) -> str | None:
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            path = tmp.name
            tmp.close()
            with wave.open(path, "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes((audio * 32767).astype(np.int16).tobytes())
            return path
        except Exception:
            return None
