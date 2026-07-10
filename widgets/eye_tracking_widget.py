from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from stream_state import EyeTrackingSample, PupilSample
from widgets.theme import make_chip, set_chip, set_widget_property


class EyeTrackingWidget(QWidget):
    """Gaze / blink metrics computed from the real EyeGaze stream.

    Every row shows N/A until the corresponding real signal arrives. Pupil
    diameter is not exposed by the live Gen 2 EyeGaze callback, so in real
    mode that row stays N/A by design (mock mode fills it with mock data).
    """

    def __init__(self):
        super().__init__()
        self.title = QLabel("EYE TRACKING · GAZE")
        self.title.setObjectName("panelTitle")
        self.state_chip = make_chip("WAITING", tone="")

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(self.title, 1)
        header.addWidget(self.state_chip, 0)

        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(5)

        self._rows: dict[str, QLabel] = {}
        for row, (key, caption) in enumerate(
            (
                ("looking", "Looking"),
                ("gaze", "Yaw / Pitch"),
                ("depth", "Depth"),
                ("blink", "Blink rate"),
                ("perclos", "PERCLOS (30 s)"),
                ("pupils", "Pupil diameter"),
            )
        ):
            label = QLabel(caption)
            label.setObjectName("metricLabel")
            value = QLabel("N/A")
            value.setObjectName("metricValue")
            value.setProperty("tone", "na")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(label, row, 0)
            grid.addWidget(value, row, 1)
            self._rows[key] = value
        grid.setColumnStretch(1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addLayout(grid)

    def _set_row(self, key: str, text: str, tone: str = "") -> None:
        value = self._rows[key]
        value.setText(text)
        set_widget_property(value, "tone", tone)

    def update_sample(
        self,
        sample: Optional[EyeTrackingSample],
        pupil: Optional[PupilSample],
        stale: bool = False,
    ) -> None:
        if sample is None:
            set_chip(self.state_chip, "WAITING", "")
            for key in ("looking", "gaze", "depth", "blink", "perclos"):
                self._set_row(key, "N/A", "na")
        else:
            if stale:
                set_chip(self.state_chip, "STALE", "warn")
            elif sample.combined_gaze_valid is False:
                set_chip(self.state_chip, sample.eye_state.upper(), "warn")
            elif sample.combined_gaze_valid:
                set_chip(self.state_chip, sample.eye_state.upper(), "good")
            else:
                set_chip(self.state_chip, "WAITING", "")

            self._set_row(
                "looking",
                sample.looking_state if sample.looking_state else "N/A",
                "" if sample.looking_state else "na",
            )
            if sample.yaw_rad is None or sample.pitch_rad is None:
                self._set_row("gaze", "N/A", "na")
            else:
                self._set_row(
                    "gaze",
                    f"{math.degrees(sample.yaw_rad):+.1f}° / {math.degrees(sample.pitch_rad):+.1f}°",
                )
            if sample.depth_m is None:
                self._set_row("depth", "N/A", "na")
            else:
                self._set_row("depth", f"{sample.depth_m:.2f} m")
            if sample.blink_rate_per_min is None:
                self._set_row("blink", "N/A", "na")
            else:
                self._set_row("blink", f"{sample.blink_rate_per_min:.0f} /min")
            if sample.perclos is None:
                self._set_row("perclos", "N/A", "na")
            else:
                perclos_pct = sample.perclos * 100.0
                self._set_row(
                    "perclos",
                    f"{perclos_pct:.0f} %",
                    "warn" if perclos_pct >= 25.0 else "",
                )

        if (
            pupil is None
            or (pupil.left_diameter_mm is None and pupil.right_diameter_mm is None)
        ):
            self._set_row("pupils", "N/A · not in live SDK", "na")
        else:
            left = "--" if pupil.left_diameter_mm is None else f"{pupil.left_diameter_mm:.1f}"
            right = "--" if pupil.right_diameter_mm is None else f"{pupil.right_diameter_mm:.1f}"
            self._set_row("pupils", f"L {left} / R {right} mm")
