from __future__ import annotations

import math
import time
from typing import Iterable, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from stream_state import HeartRateSample, PulseVariabilitySample
from widgets.theme import Colors


class HeartRateWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.title = QLabel("Heart Rate")
        self.title.setObjectName("panelTitle")
        self.bpm = QLabel("--")
        self.bpm.setObjectName("bpmValue")
        self.quality = QLabel("PPG not available")
        self.trend = QLabel("Trend: --")
        self.variability = QLabel("PV: Not enough data")
        self.plot = _BpmTrendPlot()

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.addWidget(self.title)
        layout.addWidget(self.bpm)
        layout.addWidget(self.quality)
        layout.addWidget(self.trend)
        layout.addWidget(self.variability)
        layout.addWidget(self.plot, 1)

    def update_sample(
        self,
        sample: HeartRateSample | None,
        variability: PulseVariabilitySample | None,
    ) -> None:
        if sample is None or sample.bpm is None:
            self.bpm.setText("-- BPM")
            message = "PPG not available" if sample is None else sample.message or "Waiting for stable BPM"
            self.quality.setText(message)
            self.trend.setText("Trend: --")
            self.plot.set_status(message)
        else:
            self.bpm.setText(f"{sample.bpm:.0f} BPM")
            self.quality.setText(
                f"Signal: {sample.quality} ({sample.quality_score:.2f})"
            )
            self.trend.setText(f"Trend: {sample.trend}")
            self.plot.add_bpm(sample.timestamp_s or time.monotonic(), sample.bpm)

        if variability is None or variability.rmssd_ms is None:
            text = "PV: Not enough data"
            if variability is not None:
                text = f"PV: {variability.status}"
            self.variability.setText(text)
        else:
            self.variability.setText(
                f"PV: {variability.rmssd_ms:.0f} ms ({variability.status})"
            )


class _BpmTrendPlot(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(122)
        self.setMaximumHeight(150)
        self._history: list[Tuple[float, float]] = []
        self._status = "Waiting for BPM..."
        self._window_s = 60.0

    def add_bpm(self, timestamp_s: float, bpm: float) -> None:
        if not math.isfinite(bpm):
            return
        if not self._history or timestamp_s - self._history[-1][0] >= 0.8:
            self._history.append((timestamp_s, float(bpm)))
        else:
            self._history[-1] = (timestamp_s, float(bpm))
        cutoff = timestamp_s - self._window_s
        self._history = [(t, v) for t, v in self._history if t >= cutoff]
        self._status = ""
        self.update()

    def set_status(self, status: str) -> None:
        self._status = status
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.fillRect(rect, QColor(Colors.CANVAS))
        painter.setPen(QPen(QColor(Colors.CANVAS_BORDER), 1))
        painter.drawRect(rect)
        plot = rect.adjusted(50, 12, -12, -24)

        if len(self._history) < 2:
            min_y, max_y = 40.0, 180.0
            self._draw_axes(painter, plot, min_y, max_y)
            self._draw_y_ticks(painter, plot, min_y, max_y)
            if self._history:
                bpm = self._history[-1][1]
                span_y = max(1e-6, max_y - min_y)
                y = plot.bottom() - ((bpm - min_y) / span_y) * plot.height()
            else:
                y = plot.center().y()
            painter.setPen(QPen(QColor(Colors.TEXT_MUTED), 2, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(plot.left(), float(y)), QPointF(plot.right(), float(y)))
            painter.setPen(QColor(Colors.TEXT_MUTED))
            if not self._history:
                painter.drawText(plot.adjusted(4, 0, -4, -4), Qt.AlignRight | Qt.AlignBottom, self._status)
            return

        latest_t = self._history[-1][0]
        points = [(t - latest_t, bpm) for t, bpm in self._history]
        ys = [p[1] for p in points]
        min_y, max_y = self._bpm_bounds(ys)
        span_y = max(1e-6, max_y - min_y)
        path = QPainterPath()
        for i, (x, y) in enumerate(points):
            px = plot.left() + ((x + self._window_s) / self._window_s) * plot.width()
            py = plot.bottom() - ((y - min_y) / span_y) * plot.height()
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        self._draw_axes(painter, plot, min_y, max_y)
        self._draw_y_ticks(painter, plot, min_y, max_y)
        painter.setPen(QPen(QColor(Colors.SUCCESS), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)
        painter.setBrush(QColor(Colors.SUCCESS))
        painter.setPen(QPen(QColor(Colors.BACKGROUND), 1))
        last_x = plot.left() + ((points[-1][0] + self._window_s) / self._window_s) * plot.width()
        last_y = plot.bottom() - ((points[-1][1] - min_y) / span_y) * plot.height()
        painter.drawEllipse(QRectF(last_x - 3, last_y - 3, 6, 6))

    def _draw_axes(self, painter: QPainter, plot, min_y: float, max_y: float) -> None:
        painter.setPen(QPen(QColor(Colors.BORDER_STRONG), 1))
        painter.drawLine(plot.left(), plot.top(), plot.left(), plot.bottom())
        painter.drawLine(plot.left(), plot.bottom(), plot.right(), plot.bottom())
        painter.setPen(QColor(Colors.TEXT_MUTED))
        painter.drawText(plot.left(), plot.bottom() + 18, "-60 s")
        painter.drawText(plot.right() - 30, plot.bottom() + 18, "now")
        painter.drawText(plot.right() - 64, plot.top() + 12, f"{max_y:.0f} BPM")

    def _draw_y_ticks(self, painter: QPainter, plot, min_y: float, max_y: float) -> None:
        ticks = [min_y, (min_y + max_y) / 2.0, max_y]
        span = max(1e-6, max_y - min_y)
        for tick in ticks:
            y = plot.bottom() - ((tick - min_y) / span) * plot.height()
            painter.setPen(QPen(QColor(Colors.CANVAS_BORDER), 1))
            painter.drawLine(plot.left(), int(y), plot.right(), int(y))
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.drawText(4, int(y) + 4, f"{tick:.0f}")

    @staticmethod
    def _bpm_bounds(values: Iterable[float]) -> Tuple[float, float]:
        vals = list(values)
        lo = min(vals)
        hi = max(vals)
        lo = math.floor((lo - 5.0) / 5.0) * 5.0
        hi = math.ceil((hi + 5.0) / 5.0) * 5.0
        if hi - lo < 10.0:
            center = (lo + hi) / 2.0
            lo = center - 5.0
            hi = center + 5.0
        return max(30.0, lo), min(220.0, hi)
