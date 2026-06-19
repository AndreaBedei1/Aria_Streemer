from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass
class PpgQualityEstimate:
    label: str
    score: float
    message: str


def estimate_ppg_quality(values: Sequence[float], sample_rate_hz: float) -> PpgQualityEstimate:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < max(64, int(sample_rate_hz * 3)):
        return PpgQualityEstimate("NOT AVAILABLE", 0.0, "Not enough PPG data")

    centered = arr - np.median(arr)
    amplitude = float(np.percentile(centered, 95) - np.percentile(centered, 5))
    std = float(np.std(centered))
    if amplitude <= 1e-6 or std <= 1e-6:
        return PpgQualityEstimate("POOR", 0.05, "Flat or missing contact")

    diffs = np.diff(centered)
    noise_ratio = float(np.std(diffs) / (std + 1e-6))
    saturation_ratio = float(
        max(np.mean(arr <= np.percentile(arr, 1)), np.mean(arr >= np.percentile(arr, 99)))
    )

    freqs = np.fft.rfftfreq(arr.size, d=1.0 / sample_rate_hz)
    spectrum = np.abs(np.fft.rfft(centered * np.hanning(arr.size)))
    band = (freqs >= 0.7) & (freqs <= 3.0)
    if not np.any(band):
        return PpgQualityEstimate("POOR", 0.1, "No heart-rate band")

    band_power = float(np.sum(spectrum[band] ** 2))
    total_power = float(np.sum(spectrum**2) + 1e-6)
    periodicity = band_power / total_power

    amp_score = np.clip(amplitude / (std * 4.0 + 1e-6), 0.0, 1.0)
    noise_score = np.clip(1.7 - noise_ratio, 0.0, 1.0)
    periodicity_score = np.clip(periodicity * 4.0, 0.0, 1.0)
    saturation_score = np.clip(1.0 - saturation_ratio * 20.0, 0.0, 1.0)
    score = float(
        0.25 * amp_score
        + 0.25 * noise_score
        + 0.35 * periodicity_score
        + 0.15 * saturation_score
    )

    if score >= 0.68:
        label = "GOOD"
    elif score >= 0.38:
        label = "MEDIUM"
    else:
        label = "POOR"
    return PpgQualityEstimate(label, score, f"periodicity={periodicity:.2f}")
