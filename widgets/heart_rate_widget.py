from __future__ import annotations

import math
import time
from typing import Iterable, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from stream_state import HeartRateSample, PulseVariabilitySample
from widgets.theme import Colors, make_chip, set_chip, set_widget_property


_TREND_ARROWS = {"rising": "▲", "falling": "▼", "stable": "→"}


class HeartRateWidget(QWidget):
    """BPM derived from the real PPG stream; explicit about missing data."""

    def __init__(self):
        super().__init__()
        self.title = QLabel("HEART RATE · PPG")
        self.title.setObjectName("panelTitle")
        self.source_chip = make_chip("PPG", tone="")

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(self.title, 1)
        header.addWidget(self.source_chip, 0)

        self.bpm = QLabel("--")
        self.bpm.setObjectName("heroValue")
        self.bpm.setProperty("tone", "waiting")
        self.unit = QLabel("BPM")
        self.unit.setObjectName("heroUnit")
        self.trend = QLabel("")
        self.trend.setObjectName("heroUnit")

        value_row = QHBoxLayout()
        value_row.setContentsMargins(0, 0, 0, 0)
        value_row.setSpacing(8)
        value_row.addWidget(self.bpm, 0, Qt.AlignBottom)
        value_row.addWidget(self.unit, 0, Qt.AlignBottom)
        value_row.addStretch(1)
        value_row.addWidget(self.trend, 0, Qt.AlignBottom)

        self.quality = QLabel("Waiting for real PPG data...")
        self.quality.setObjectName("metricValue")
        self.quality.setProperty("tone", "na")
        self.variability = QLabel("Pulse variability: N/A")
        self.variability.setObjectName("metricLabel")

        self.plot = _BpmTrendPlot()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addLayout(value_row)
        layout.addWidget(self.quality)
        layout.addWidget(self.variability)
        layout.addWidget(self.plot, 1)

    def update_sample(
        self,
        sample: HeartRateSample | None,
        variability: PulseVariabilitySample | None,
    ) -> None:
        if sample is None or sample.bpm is None:
            self.bpm.setText("--")
            set_widget_property(self.bpm, "tone", "waiting")
            self.trend.setText("")
            message = (
                "Waiting for real PPG data..."
                if sample is None
                else (sample.message or "PPG received, waiting for a stable pulse...")
            )
            self.quality.setText(message)
            set_widget_property(self.quality, "tone", "na")
            set_chip(self.source_chip, sample.source if sample else "PPG", "")
            self.plot.set_status(message)
        else:
            self.bpm.setText(f"{sample.bpm:.0f}")
            set_widget_property(self.bpm, "tone", "")
            self.trend.setText(_TREND_ARROWS.get(sample.trend, ""))
            self.quality.setText(
                f"Signal {sample.quality} · score {sample.quality_score:.2f}"
            )
            tone = "good" if sample.quality == "GOOD" else ("warn" if sample.quality == "FAIR" else "na")
            set_widget_property(self.quality, "tone", tone)
            set_chip(self.source_chip, sample.source, "good" if sample.quality == "GOOD" else "")
            self.plot.add_bpm(sample.timestamp_s or time.monotonic(), sample.bpm)

        if variability is None or variability.rmssd_ms is None:
            status = variability.status if variability else "N/A"
            self.variability.setText(f"Pulse variability: {status or 'N/A'}")
        else:
            self.variability.setText(
                f"Pulse variability: RMSSD {variability.rmssd_ms:.0f} ms · {variability.peak_count} beats"
            )


class _BpmTrendPlot(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(110)
        self.setMaximumHeight(150)
        self._history: list[Tuple[float, float]] = []
        self._status = "Waiting for real PPG data..."
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
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(Colors.CANVAS))
        painter.drawRoundedRect(rect, 7, 7)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(Colors.CANVAS_BORDER), 1))
        painter.drawRoundedRect(rect, 7, 7)
        plot = rect.adjusted(44, 12, -12, -22)

        if len(self._history) < 2:
            min_y, max_y = 40.0, 180.0
            self._draw_grid(painter, plot, min_y, max_y)
            painter.setPen(QColor(Colors.TEXT_SUBTLE))
            painter.drawText(plot, Qt.AlignCenter, self._status or "Collecting samples...")
            return

        latest_t = self._history[-1][0]
        points = [(t - latest_t, bpm) for t, bpm in self._history]
        ys = [p[1] for p in points]
        min_y, max_y = self._bpm_bounds(ys)
        span_y = max(1e-6, max_y - min_y)
        self._draw_grid(painter, plot, min_y, max_y)

        path = QPainterPath()
        for i, (x, y) in enumerate(points):
            px = plot.left() + ((x + self._window_s) / self._window_s) * plot.width()
            py = plot.bottom() - ((y - min_y) / span_y) * plot.height()
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)

        # Soft area fill below the line.
        area = QPainterPath(path)
        last_px = plot.left() + ((points[-1][0] + self._window_s) / self._window_s) * plot.width()
        first_px = plot.left() + ((points[0][0] + self._window_s) / self._window_s) * plot.width()
        area.lineTo(last_px, plot.bottom())
        area.lineTo(first_px, plot.bottom())
        area.closeSubpath()
        fill = QColor(Colors.SUCCESS)
        fill.setAlpha(26)
        painter.fillPath(area, fill)

        painter.setPen(QPen(QColor(Colors.SUCCESS), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)
        painter.setBrush(QColor(Colors.SUCCESS))
        painter.setPen(QPen(QColor(Colors.BACKGROUND), 1))
        last_y = plot.bottom() - ((points[-1][1] - min_y) / span_y) * plot.height()
        painter.drawEllipse(QRectF(last_px - 3.2, last_y - 3.2, 6.4, 6.4))

    def _draw_grid(self, painter: QPainter, plot, min_y: float, max_y: float) -> None:
        ticks = [min_y, (min_y + max_y) / 2.0, max_y]
        span = max(1e-6, max_y - min_y)
        for tick in ticks:
            y = plot.bottom() - ((tick - min_y) / span) * plot.height()
            painter.setPen(QPen(QColor(Colors.CANVAS_BORDER), 1, Qt.DashLine))
            painter.drawLine(plot.left(), int(y), plot.right(), int(y))
            painter.setPen(QColor(Colors.TEXT_SUBTLE))
            painter.drawText(6, int(y) + 4, f"{tick:.0f}")
        painter.setPen(QColor(Colors.TEXT_SUBTLE))
        painter.drawText(plot.left(), plot.bottom() + 15, "-60 s")
        painter.drawText(plot.right() - 26, plot.bottom() + 15, "now")

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
