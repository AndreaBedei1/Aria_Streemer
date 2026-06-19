from __future__ import annotations

from collections import deque
from typing import Deque, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from stream_state import EyeTrackingSample, PupilSample


class EyeTrackingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.title = QLabel("Eye tracking")
        self.title.setObjectName("panelTitle")
        self.state = QLabel("Waiting for data...")
        self.gaze = QLabel("Yaw/Pitch: --")
        self.blink = QLabel("Blink: --")
        self.pupil = QLabel("Pupils: not available")
        self.plot = _PupilPlot()
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.addWidget(self.title)
        layout.addWidget(self.state)
        layout.addWidget(self.gaze)
        layout.addWidget(self.blink)
        layout.addWidget(self.pupil)
        layout.addWidget(self.plot)

    def update_sample(
        self,
        sample: Optional[EyeTrackingSample],
        pupil: Optional[PupilSample],
    ) -> None:
        if sample is None:
            self.state.setText("Eye tracking not available")
            self.gaze.setText("Yaw/Pitch: --")
            self.blink.setText("Blink: --")
        else:
            self.state.setText(f"{sample.eye_state} | {sample.looking_state}")
            yaw = "--" if sample.yaw_rad is None else f"{sample.yaw_rad:+.3f}"
            pitch = "--" if sample.pitch_rad is None else f"{sample.pitch_rad:+.3f}"
            self.gaze.setText(f"Yaw/Pitch: {yaw} / {pitch} rad")
            blink_rate = "--" if sample.blink_rate_per_min is None else f"{sample.blink_rate_per_min:.0f}"
            perclos = "--" if sample.perclos is None else f"{sample.perclos * 100:.0f}%"
            self.blink.setText(f"Blink/min: {blink_rate} | PERCLOS: {perclos}")

        if pupil is None:
            self.pupil.setText("Pupils: not available")
        else:
            left = "--" if pupil.left_diameter_mm is None else f"{pupil.left_diameter_mm:.1f}"
            right = "--" if pupil.right_diameter_mm is None else f"{pupil.right_diameter_mm:.1f}"
            lux = "--" if pupil.ambient_lux is None else f"{pupil.ambient_lux:.0f} lux"
            self.pupil.setText(f"Pupils L/R: {left} / {right} mm | {lux}")
            if pupil.left_diameter_mm is not None or pupil.right_diameter_mm is not None:
                value = pupil.left_diameter_mm or pupil.right_diameter_mm or 0.0
                self.plot.add_value(value)


class _PupilPlot(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(58)
        self._values: Deque[float] = deque(maxlen=80)

    def add_value(self, value: float) -> None:
        self._values.append(value)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.fillRect(rect, QColor("#0f151d"))
        painter.setPen(QPen(QColor("#273445"), 1))
        painter.drawRect(rect)
        if len(self._values) < 2:
            painter.setPen(QColor("#92a0b3"))
            painter.drawText(rect, Qt.AlignCenter, "Pupil trend")
            return
        values = list(self._values)
        min_v, max_v = min(values), max(values)
        span = max(0.1, max_v - min_v)
        path = QPainterPath()
        for i, value in enumerate(values):
            x = rect.left() + i / max(1, len(values) - 1) * rect.width()
            y = rect.bottom() - (value - min_v) / span * rect.height()
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.setPen(QPen(QColor("#70d6ff"), 2))
        painter.drawPath(path)
