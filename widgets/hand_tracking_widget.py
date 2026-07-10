from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from processing.hand_projection import HAND_CONNECTIONS, project_hand_to_camera
from stream_state import HandSideSample, HandTrackingSample
from widgets.theme import Colors, make_chip, set_chip


class HandTrackingWidget(QWidget):
    """Skeleton view of the on-device hand tracking result."""

    def __init__(self):
        super().__init__()
        self.title = QLabel("HAND TRACKING")
        self.title.setObjectName("panelTitle")
        self.state_chip = make_chip("WAITING", tone="")

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(self.title, 1)
        header.addWidget(self.state_chip, 0)

        self.canvas = _HandsCanvas()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self.canvas, 1)

    def update_sample(
        self, sample: Optional[HandTrackingSample], stale: bool = False
    ) -> None:
        self.canvas.set_sample(sample)
        if sample is None:
            set_chip(self.state_chip, "WAITING", "")
            self.canvas.set_message("Waiting for real hand data...")
            return
        if stale:
            set_chip(self.state_chip, "STALE", "warn")
            self.canvas.set_message("")
            return
        visible = []
        if sample.left.visible:
            visible.append("L")
        if sample.right.visible:
            visible.append("R")
        if visible:
            set_chip(self.state_chip, " + ".join(visible) + " TRACKED", "good")
            self.canvas.set_message("")
        else:
            set_chip(self.state_chip, "NOT VISIBLE", "")
            self.canvas.set_message("Hands not visible in the camera view")


class _HandsCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(170)
        self._sample: HandTrackingSample | None = None
        self._message = "Waiting for real hand data..."

    def set_sample(self, sample: HandTrackingSample | None) -> None:
        self._sample = sample
        self.update()

    def set_message(self, message: str) -> None:
        if message != self._message:
            self._message = message
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

        has_landmarks = self._sample is not None and self._sample.landmark_count > 0
        if not has_landmarks:
            if self._message:
                painter.setPen(QColor(Colors.TEXT_SUBTLE))
                painter.drawText(rect, Qt.AlignCenter, self._message)
            return

        mid = rect.center().x()
        left_rect = rect.adjusted(10, 10, -(rect.width() // 2 + 5), -10)
        right_rect = rect.adjusted(rect.width() // 2 + 5, 10, -10, -10)
        painter.setPen(QPen(QColor(Colors.CANVAS_BORDER), 1, Qt.DashLine))
        painter.drawLine(mid, rect.top() + 10, mid, rect.bottom() - 10)

        painter.setPen(QColor(Colors.TEXT_SUBTLE))
        painter.drawText(left_rect.adjusted(2, 0, 0, 0), Qt.AlignLeft | Qt.AlignTop, "LEFT")
        painter.drawText(right_rect.adjusted(0, 0, -2, 0), Qt.AlignRight | Qt.AlignTop, "RIGHT")

        self._draw_side(painter, left_rect, self._sample.left, QColor(Colors.INFO))
        self._draw_side(painter, right_rect, self._sample.right, QColor(Colors.WARNING))

    def _draw_side(self, painter: QPainter, rect, side: HandSideSample, color: QColor) -> None:
        if not side.visible or not side.landmarks_device:
            painter.setPen(QColor(Colors.TEXT_SUBTLE))
            painter.drawText(rect, Qt.AlignCenter, "—")
            return
        drawing_rect = rect.adjusted(4, 14, -4, -4)
        projected = project_hand_to_camera(
            side.landmarks_device,
            drawing_rect.width(),
            drawing_rect.height(),
            mirror_x=False,
        )
        shifted = self._fit_points(projected, drawing_rect)
        glow = QColor(color)
        glow.setAlpha(60)
        painter.setPen(QPen(glow, 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for a, b in HAND_CONNECTIONS:
            if a < len(shifted) and b < len(shifted):
                painter.drawLine(shifted[a], shifted[b])

        painter.setPen(QPen(color, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for a, b in HAND_CONNECTIONS:
            if a < len(shifted) and b < len(shifted):
                painter.drawLine(shifted[a], shifted[b])

        painter.setBrush(color)
        painter.setPen(QPen(QColor(Colors.BACKGROUND), 1.1))
        for point in shifted:
            painter.drawEllipse(point, 3.4, 3.4)

        if side.confidence is not None:
            painter.setPen(QColor(Colors.TEXT_SUBTLE))
            painter.drawText(
                rect.adjusted(0, 0, 0, -2),
                Qt.AlignHCenter | Qt.AlignBottom,
                f"conf {side.confidence:.2f}",
            )

    def _fit_points(self, points: list[tuple[float, float]], rect) -> list[QPointF]:
        if not points:
            return []
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(1.0, max_x - min_x)
        span_y = max(1.0, max_y - min_y)
        scale = min(rect.width() / span_x, rect.height() / span_y) * 0.8
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
