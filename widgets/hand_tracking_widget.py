from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from processing.hand_projection import HAND_CONNECTIONS, project_hand_to_camera
from stream_state import HandSideSample, HandTrackingSample
from widgets.theme import Colors


class HandTrackingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.title = QLabel("Hand tracking")
        self.title.setObjectName("panelTitle")
        self.canvas = _HandsCanvas()
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.addWidget(self.title)
        layout.addWidget(self.canvas)

    def update_sample(self, sample: HandTrackingSample | None) -> None:
        if sample is None:
            self.canvas.set_sample(None)
            return
        self.canvas.set_sample(sample)


class _HandsCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(210)
        self._sample: HandTrackingSample | None = None

    def set_sample(self, sample: HandTrackingSample | None) -> None:
        self._sample = sample
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.fillRect(rect, QColor(Colors.CANVAS))
        painter.setPen(QPen(QColor(Colors.CANVAS_BORDER), 1))
        painter.drawRect(rect)
        if self._sample is None or self._sample.landmark_count == 0:
            return
        mid = rect.center().x()
        left_rect = rect.adjusted(8, 8, -(rect.width() // 2 + 4), -8)
        right_rect = rect.adjusted(rect.width() // 2 + 4, 8, -8, -8)
        self._draw_hand_area(painter, left_rect)
        self._draw_hand_area(painter, right_rect)
        self._draw_side(painter, left_rect, self._sample.left, QColor(Colors.INFO))
        self._draw_side(painter, right_rect, self._sample.right, QColor(Colors.WARNING))
        painter.setPen(QPen(QColor(Colors.CANVAS_BORDER), 1))
        painter.drawLine(mid, rect.top() + 8, mid, rect.bottom() - 8)

    def _draw_hand_area(self, painter: QPainter, rect) -> None:
        fill = QColor(255, 255, 255, 10)
        painter.fillRect(rect.adjusted(2, 2, -2, -2), fill)

    def _draw_side(self, painter: QPainter, rect, side: HandSideSample, color: QColor) -> None:
        if not side.visible or not side.landmarks_device:
            return
        drawing_rect = rect.adjusted(4, 4, -4, -4)
        projected = project_hand_to_camera(
            side.landmarks_device,
            drawing_rect.width(),
            drawing_rect.height(),
            mirror_x=False,
        )
        shifted = self._fit_points(projected, drawing_rect)
        glow = QColor(color)
        glow.setAlpha(70)
        painter.setPen(QPen(glow, 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for a, b in HAND_CONNECTIONS:
            if a < len(shifted) and b < len(shifted):
                painter.drawLine(shifted[a], shifted[b])

        painter.setPen(QPen(color, 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for a, b in HAND_CONNECTIONS:
            if a < len(shifted) and b < len(shifted):
                painter.drawLine(shifted[a], shifted[b])

        painter.setBrush(color)
        painter.setPen(QPen(QColor(Colors.BACKGROUND), 1.2))
        for point in shifted:
            painter.drawEllipse(point, 4.0, 4.0)

    def _fit_points(self, points: list[tuple[float, float]], rect) -> list[QPointF]:
        if not points:
            return []
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(1.0, max_x - min_x)
        span_y = max(1.0, max_y - min_y)
        scale = min(rect.width() / span_x, rect.height() / span_y) * 0.84
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        target = rect.center()
        return [
            QPointF(
                target.x() + (x - cx) * scale,
                target.y() + (y - cy) * scale,
            )
            for x, y in points
        ]
