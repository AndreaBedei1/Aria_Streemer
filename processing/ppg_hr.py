from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

import numpy as np

from processing.downsampling import decimate_points
from processing.ppg_quality import PpgQualityEstimate, estimate_ppg_quality

try:
    from scipy.signal import butter, filtfilt, find_peaks
except Exception:  # pragma: no cover - fallback path
    butter = filtfilt = find_peaks = None


@dataclass
class HeartRateEstimate:
    bpm: Optional[float]
    quality: PpgQualityEstimate
    trend: str
    peak_times_s: List[float] = field(default_factory=list)
    plot_points: List[Tuple[float, float]] = field(default_factory=list)
    message: str = ""


class PpgHeartRateEstimator:
    def __init__(
        self,
        sample_rate_hz: float = 256.0,
        window_s: float = 10.0,
        min_bpm: float = 42.0,
        max_bpm: float = 190.0,
    ):
        self.sample_rate_hz = sample_rate_hz
        self.window_s = window_s
        self.min_bpm = min_bpm
        self.max_bpm = max_bpm
        self._samples: Deque[Tuple[float, float]] = deque()
        self._history: Deque[Tuple[float, float]] = deque(maxlen=30)

    def add_sample(self, timestamp_s: float, value: float) -> None:
        if not np.isfinite(value):
            return
        self._samples.append((timestamp_s, float(value)))
        cutoff = timestamp_s - self.window_s
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def clear(self) -> None:
        self._samples.clear()
        self._history.clear()

    def estimate(self) -> HeartRateEstimate:
        if len(self._samples) < max(64, int(self.sample_rate_hz * 4)):
            q = PpgQualityEstimate("NOT AVAILABLE", 0.0, "Not enough PPG data")
            return HeartRateEstimate(None, q, "unknown", message=q.message)

        times = np.asarray([t for t, _ in self._samples], dtype=float)
        values = np.asarray([v for _, v in self._samples], dtype=float)
        quality = estimate_ppg_quality(values, self.sample_rate_hz)
        if quality.label in {"POOR", "NOT AVAILABLE"}:
            return HeartRateEstimate(
                None,
                quality,
                "unknown",
                plot_points=self._plot_points(times, values),
                message=quality.message,
            )

        filtered = self._filter(values)
        peak_bpm, peak_times = self._estimate_from_peaks(times, filtered)
        fft_bpm = self._estimate_from_fft(filtered)
        bpm = self._select_bpm(peak_bpm, fft_bpm, quality)

        if bpm is not None:
            now = time.monotonic()
            self._history.append((now, bpm))
            bpm = self._smoothed_bpm()

        return HeartRateEstimate(
            bpm=bpm,
            quality=quality,
            trend=self._trend(),
            peak_times_s=peak_times,
            plot_points=self._plot_points(times, filtered),
            message="" if bpm is not None else "No stable pulse found",
        )

    def values_for_variability(self) -> Tuple[np.ndarray, np.ndarray]:
        if not self._samples:
            return np.empty(0), np.empty(0)
        times = np.asarray([t for t, _ in self._samples], dtype=float)
        values = np.asarray([v for _, v in self._samples], dtype=float)
        return times, self._filter(values)

    def _filter(self, values: np.ndarray) -> np.ndarray:
        centered = values - np.median(values)
        if butter is None or filtfilt is None or len(centered) < 32:
            return centered
        nyq = 0.5 * self.sample_rate_hz
        low = (self.min_bpm / 60.0) / nyq
        high = (self.max_bpm / 60.0) / nyq
        try:
            b, a = butter(2, [low, high], btype="band")
            return filtfilt(b, a, centered)
        except Exception:
            return centered

    def _estimate_from_peaks(
        self, times: np.ndarray, filtered: np.ndarray
    ) -> Tuple[Optional[float], List[float]]:
        if find_peaks is None or filtered.size < 4:
            return None, []
        min_distance = int(self.sample_rate_hz * 60.0 / self.max_bpm)
        prominence = max(1e-6, np.std(filtered) * 0.35)
        peaks, _ = find_peaks(filtered, distance=min_distance, prominence=prominence)
        if peaks.size < 4:
            return None, []
        peak_times = times[peaks].tolist()
        intervals = np.diff(peak_times)
        intervals = intervals[(intervals >= 60.0 / self.max_bpm) & (intervals <= 60.0 / self.min_bpm)]
        if intervals.size < 3:
            return None, peak_times
        bpm = float(60.0 / np.median(intervals))
        if self.min_bpm <= bpm <= self.max_bpm:
            return bpm, peak_times
        return None, peak_times

    def _estimate_from_fft(self, filtered: np.ndarray) -> Optional[float]:
        if filtered.size < 64:
            return None
        freqs = np.fft.rfftfreq(filtered.size, d=1.0 / self.sample_rate_hz)
        spectrum = np.abs(np.fft.rfft(filtered * np.hanning(filtered.size)))
        band = (freqs >= self.min_bpm / 60.0) & (freqs <= self.max_bpm / 60.0)
        if not np.any(band):
            return None
        freq = float(freqs[band][np.argmax(spectrum[band])])
        bpm = freq * 60.0
        return bpm if self.min_bpm <= bpm <= self.max_bpm else None

    def _select_bpm(
        self,
        peak_bpm: Optional[float],
        fft_bpm: Optional[float],
        quality: PpgQualityEstimate,
    ) -> Optional[float]:
        if peak_bpm is None and fft_bpm is None:
            return None
        if peak_bpm is not None and fft_bpm is not None:
            disagreement = abs(peak_bpm - fft_bpm)
            if disagreement <= 12.0:
                bpm = 0.75 * peak_bpm + 0.25 * fft_bpm
            elif quality.label == "GOOD":
                bpm = peak_bpm
            else:
                return self._recent_median_bpm()
        else:
            bpm = peak_bpm if peak_bpm is not None else fft_bpm

        recent = self._recent_median_bpm()
        if recent is not None and bpm is not None:
            jump = abs(bpm - recent)
            if jump > 24.0 and quality.label != "GOOD":
                return recent
            if jump > 14.0:
                bpm = 0.65 * bpm + 0.35 * recent
        return bpm

    def _recent_median_bpm(self) -> Optional[float]:
        if not self._history:
            return None
        recent = [b for _, b in list(self._history)[-5:]]
        return float(np.median(recent))

    def _smoothed_bpm(self) -> Optional[float]:
        if not self._history:
            return None
        recent = [b for _, b in list(self._history)[-5:]]
        return float(np.median(recent))

    def _trend(self) -> str:
        if len(self._history) < 5:
            return "stable"
        recent = [b for _, b in list(self._history)[-5:]]
        delta = recent[-1] - recent[0]
        if delta > 3.0:
            return "in aumento"
        if delta < -3.0:
            return "in diminuzione"
        return "stabile"

    def _plot_points(self, times: np.ndarray, values: np.ndarray) -> List[Tuple[float, float]]:
        if times.size == 0:
            return []
        rel = times - times[-1]
        pts = list(zip(rel.tolist(), values.tolist()))
        return decimate_points(pts, 240)
