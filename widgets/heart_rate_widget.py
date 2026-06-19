from __future__ import annotations

from typing import Iterable, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from stream_state import HeartRateSample, PulseVariabilitySample


class HeartRateWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.title = QLabel("Heart rate")
        self.title.setObjectName("panelTitle")
        self.bpm = QLabel("--")
        self.bpm.setObjectName("bpmValue")
        self.quality = QLabel("PPG not available")
        self.trend = QLabel("Trend: --")
        self.variability = QLabel("Pulse variability: Not enough data")
        self.plot = _MiniPlot()
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.addWidget(self.title)
        layout.addWidget(self.bpm)
        layout.addWidget(self.quality)
        layout.addWidget(self.trend)
        layout.addWidget(self.variability)
        layout.addWidget(self.plot)

    def update_sample(
        self,
        sample: HeartRateSample | None,
        variability: PulseVariabilitySample | None,
    ) -> None:
        if sample is None or sample.bpm is None:
            self.bpm.setText("-- BPM")
            self.quality.setText("PPG not available")
            self.trend.setText("Trend: --")
            self.plot.set_points([])
        else:
            self.bpm.setText(f"{sample.bpm:.0f} BPM")
            self.quality.setText(
                f"Signal: {sample.quality} ({sample.quality_score:.2f})"
            )
            self.trend.setText(f"Trend: {sample.trend}")
            self.plot.set_points(sample.ppg_plot)

        if variability is None or variability.rmssd_ms is None:
            text = "Pulse variability: Not enough data"
            if variability is not None:
                text = f"Pulse variability: {variability.status}"
            self.variability.setText(text)
        else:
            self.variability.setText(
                f"Pulse variability: {variability.rmssd_ms:.0f} ms ({variability.status})"
            )


class _MiniPlot(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(72)
        self._points: list[Tuple[float, float]] = []

    def set_points(self, points: Iterable[Tuple[float, float]]) -> None:
        self._points = list(points)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.fillRect(rect, QColor("#0f151d"))
        painter.setPen(QPen(QColor("#273445"), 1))
        painter.drawRect(rect)
        if len(self._points) < 2:
            painter.setPen(QColor("#92a0b3"))
            painter.drawText(rect, Qt.AlignCenter, "Waiting for PPG...")
            return

        xs = [p[0] for p in self._points]
        ys = [p[1] for p in self._points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(1e-6, max_x - min_x)
        span_y = max(1e-6, max_y - min_y)
        path = QPainterPath()
        for i, (x, y) in enumerate(self._points):
            px = rect.left() + ((x - min_x) / span_x) * rect.width()
            py = rect.bottom() - ((y - min_y) / span_y) * rect.height()
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        painter.setPen(QPen(QColor("#ffcf33"), 2))
        painter.drawPath(path)
