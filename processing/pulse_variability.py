from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

try:
    from scipy.signal import find_peaks
except Exception:  # pragma: no cover
    find_peaks = None


@dataclass
class PulseVariabilityEstimate:
    rmssd_ms: Optional[float]
    status: str
    peak_count: int


def estimate_pulse_variability(
    times_s: np.ndarray,
    filtered_ppg: np.ndarray,
    sample_rate_hz: float,
    quality_label: str,
    min_window_s: float = 30.0,
) -> PulseVariabilityEstimate:
    if quality_label not in {"GOOD", "MEDIUM"}:
        return PulseVariabilityEstimate(None, "Low quality", 0)
    if times_s.size < 4 or times_s[-1] - times_s[0] < min_window_s:
        return PulseVariabilityEstimate(None, "Not enough data", 0)
    if find_peaks is None:
        return PulseVariabilityEstimate(None, "SciPy peak detection unavailable", 0)

    distance = int(sample_rate_hz * 0.32)
    prominence = max(1e-6, float(np.std(filtered_ppg)) * 0.35)
    peaks, _ = find_peaks(filtered_ppg, distance=distance, prominence=prominence)
    if peaks.size < 8:
        return PulseVariabilityEstimate(None, "Not enough peaks", int(peaks.size))

    intervals_ms = np.diff(times_s[peaks]) * 1000.0
    intervals_ms = intervals_ms[(intervals_ms >= 320.0) & (intervals_ms <= 1500.0)]
    if intervals_ms.size < 6:
        return PulseVariabilityEstimate(None, "Not enough clean intervals", int(peaks.size))

    rmssd = float(np.sqrt(np.mean(np.diff(intervals_ms) ** 2)))
    return PulseVariabilityEstimate(rmssd, "experimental", int(peaks.size))
