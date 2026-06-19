from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from stream_state import VideoFrame


class VideoWidget(QWidget):
    def __init__(self, title: str = "RGB camera"):
        super().__init__()
        self._title = QLabel(title)
        self._title.setObjectName("panelTitle")
        self._canvas = _VideoCanvas()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._title)
        layout.addWidget(self._canvas, 1)

    def set_frame(
        self,
        frame: Optional[VideoFrame],
        gaze_point: Optional[Tuple[float, float]] = None,
        message: str = "Waiting for data...",
    ) -> None:
        self._canvas.set_frame(frame, gaze_point, message)


class SmallVideoWidget(QWidget):
    def __init__(self, title: str):
        super().__init__()
        self._title = QLabel(title)
        self._title.setObjectName("muted")
        self._canvas = _VideoCanvas()
        self._canvas.setMinimumSize(120, 100)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._title)
        layout.addWidget(self._canvas)

    def set_frame(self, frame: Optional[VideoFrame], message: str = "ET cameras not available") -> None:
        self._canvas.set_frame(frame, None, message)


class _VideoCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(520, 360)
        self._pixmap: Optional[QPixmap] = None
        self._frame_size: Tuple[int, int] = (0, 0)
        self._gaze_point: Optional[Tuple[float, float]] = None
        self._message = "Waiting for data..."

    def set_frame(
        self,
        frame: Optional[VideoFrame],
        gaze_point: Optional[Tuple[float, float]],
        message: str,
    ) -> None:
        self._gaze_point = gaze_point
        self._message = message
        if frame is None:
            self._pixmap = None
            self._frame_size = (0, 0)
        else:
            self._pixmap = QPixmap.fromImage(_array_to_qimage(frame.image_rgb))
            self._frame_size = (frame.width, frame.height)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#111820"))
        target = self._target_rect()
        if self._pixmap is not None:
            painter.drawPixmap(target, self._pixmap)
            self._draw_gaze(painter, target)
        else:
            painter.setPen(QColor("#d7dee8"))
            painter.drawText(self.rect(), Qt.AlignCenter, self._message)
        painter.setPen(QPen(QColor("#253241"), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def _target_rect(self) -> QRect:
        if self._pixmap is None:
            return self.rect()
        pix_size = self._pixmap.size()
        scaled = pix_size.scaled(self.size(), Qt.KeepAspectRatio)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        return QRect(x, y, scaled.width(), scaled.height())

    def _draw_gaze(self, painter: QPainter, target: QRect) -> None:
        if self._gaze_point is None or self._frame_size == (0, 0):
            return
        fw, fh = self._frame_size
        gx = target.x() + (self._gaze_point[0] / max(1, fw)) * target.width()
        gy = target.y() + (self._gaze_point[1] / max(1, fh)) * target.height()
        painter.setPen(QPen(QColor("#081018"), 3))
        painter.setBrush(QColor("#ffcf33"))
        painter.drawEllipse(int(gx) - 9, int(gy) - 9, 18, 18)
        painter.setPen(QPen(QColor("#ffcf33"), 2))
        painter.drawLine(int(gx) - 18, int(gy), int(gx) + 18, int(gy))
        painter.drawLine(int(gx), int(gy) - 18, int(gx), int(gy) + 18)


def _array_to_qimage(arr: np.ndarray) -> QImage:
    rgb = np.ascontiguousarray(arr)
    height, width = rgb.shape[:2]
    bytes_per_line = rgb.strides[0]
    image = QImage(rgb.data, width, height, bytes_per_line, QImage.Format_RGB888)
    return image.copy()
