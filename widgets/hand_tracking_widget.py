from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from processing.hand_projection import HAND_CONNECTIONS, project_hand_to_camera
from stream_state import HandSideSample, HandTrackingSample


class HandTrackingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.title = QLabel("Hand tracking")
        self.title.setObjectName("panelTitle")
        self.status = QLabel("Hand tracking not available")
        self.canvas = _HandsCanvas()
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.addWidget(self.title)
        layout.addWidget(self.status)
        layout.addWidget(self.canvas)

    def update_sample(self, sample: HandTrackingSample | None) -> None:
        if sample is None:
            self.status.setText("Hand tracking not available")
            self.canvas.set_sample(None)
            return
        left = "visible" if sample.left.visible else "not visible"
        right = "visible" if sample.right.visible else "not visible"
        self.status.setText(
            f"Left: {left} | Right: {right} | Landmarks: {sample.landmark_count}"
        )
        self.canvas.set_sample(sample)


class _HandsCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(150)
        self._sample: HandTrackingSample | None = None

    def set_sample(self, sample: HandTrackingSample | None) -> None:
        self._sample = sample
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.fillRect(rect, QColor("#0f151d"))
        painter.setPen(QPen(QColor("#273445"), 1))
        painter.drawRect(rect)
        if self._sample is None or self._sample.landmark_count == 0:
            painter.setPen(QColor("#92a0b3"))
            painter.drawText(rect, Qt.AlignCenter, "Hands not visible")
            return
        mid = rect.center().x()
        left_rect = rect.adjusted(8, 8, -(rect.width() // 2 + 4), -8)
        right_rect = rect.adjusted(rect.width() // 2 + 4, 8, -8, -8)
        self._draw_side(painter, left_rect, self._sample.left, QColor("#70d6ff"))
        self._draw_side(painter, right_rect, self._sample.right, QColor("#ffcf33"))
        painter.setPen(QPen(QColor("#273445"), 1))
        painter.drawLine(mid, rect.top() + 8, mid, rect.bottom() - 8)

    def _draw_side(self, painter: QPainter, rect, side: HandSideSample, color: QColor) -> None:
        if not side.visible or not side.landmarks_device:
            painter.setPen(QColor("#657388"))
            painter.drawText(rect, Qt.AlignCenter, "not visible")
            return
        points = project_hand_to_camera(side.landmarks_device, rect.width(), rect.height())
        shifted = [(rect.left() + x, rect.top() + y) for x, y in points]
        painter.setPen(QPen(color, 2))
        for a, b in HAND_CONNECTIONS:
            if a < len(shifted) and b < len(shifted):
                painter.drawLine(
                    int(shifted[a][0]),
                    int(shifted[a][1]),
                    int(shifted[b][0]),
                    int(shifted[b][1]),
                )
        painter.setBrush(color)
        painter.setPen(QPen(QColor("#081018"), 1))
        for x, y in shifted:
            painter.drawEllipse(int(x) - 3, int(y) - 3, 6, 6)
