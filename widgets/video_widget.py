from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from stream_state import VideoFrame
from widgets.theme import Colors


class VideoWidget(QWidget):
    """Hero camera view with gaze overlay and live-state chip."""

    def __init__(self, title: str = ""):
        super().__init__()
        self._title = QLabel(title) if title else None
        if self._title is not None:
            self._title.setObjectName("panelTitle")
        self._canvas = _VideoCanvas()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        if self._title is not None:
            layout.addWidget(self._title)
        layout.addWidget(self._canvas, 1)

    def set_frame(
        self,
        frame: Optional[VideoFrame],
        gaze_point: Optional[Tuple[float, float]] = None,
        message: str = "Waiting for real data...",
        detection_bbox: Optional[Tuple[float, float, float, float]] = None,
        live_state: str = "",
        fps: Optional[float] = None,
    ) -> None:
        self._canvas.set_frame(frame, gaze_point, message, detection_bbox, live_state, fps)


class SmallVideoWidget(QWidget):
    """Compact camera tile (eye-tracking cameras)."""

    def __init__(self, title: str):
        super().__init__()
        self._title = QLabel(title) if title else None
        if self._title is not None:
            self._title.setObjectName("panelCaption")
        self._canvas = _VideoCanvas(compact=True)
        self._canvas.setMinimumSize(120, 110)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        if self._title is not None:
            layout.addWidget(self._title)
        layout.addWidget(self._canvas, 1)

    def set_frame(
        self,
        frame: Optional[VideoFrame],
        message: str = "No signal",
        live_state: str = "",
    ) -> None:
        self._canvas.set_frame(frame, None, message, None, live_state, None)


class _VideoCanvas(QWidget):
    RADIUS = 9.0

    def __init__(self, compact: bool = False):
        super().__init__()
        self._compact = compact
        if not compact:
            self.setMinimumSize(480, 330)
        self._pixmap: Optional[QPixmap] = None
        self._frame_size: Tuple[int, int] = (0, 0)
        self._frame_label = ""
        self._frame_warning = ""
        self._gaze_point: Optional[Tuple[float, float]] = None
        self._detection_bbox: Optional[Tuple[float, float, float, float]] = None
        self._message = "Waiting for real data..."
        self._live_state = ""
        self._fps: Optional[float] = None

    def set_frame(
        self,
        frame: Optional[VideoFrame],
        gaze_point: Optional[Tuple[float, float]],
        message: str,
        detection_bbox: Optional[Tuple[float, float, float, float]] = None,
        live_state: str = "",
        fps: Optional[float] = None,
    ) -> None:
        self._gaze_point = gaze_point
        self._detection_bbox = detection_bbox
        self._message = message
        self._live_state = live_state
        self._fps = fps
        if frame is None:
            self._pixmap = None
            self._frame_size = (0, 0)
            self._frame_label = ""
            self._frame_warning = ""
        else:
            self._frame_warning = frame.warning or ""
            self._frame_label = frame.label
            if not frame.valid:
                self._pixmap = None
                self._frame_size = (0, 0)
                self._message = self._frame_warning or "Invalid frame rejected"
            else:
                try:
                    self._pixmap = QPixmap.fromImage(_array_to_qimage(frame.image_rgb))
                    self._frame_size = (frame.width, frame.height)
                except Exception as exc:
                    self._pixmap = None
                    self._frame_size = (0, 0)
                    self._message = f"Invalid frame: {exc}"
        self.update()

    # ------------------------------------------------------------- painting

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(outer, self.RADIUS, self.RADIUS)
        painter.setClipPath(clip)
        painter.fillRect(self.rect(), QColor(Colors.CANVAS_ALT))

        target = self._target_rect()
        if self._pixmap is not None:
            painter.drawPixmap(target, self._pixmap)
            self._draw_detection_box(painter, target)
            self._draw_gaze(painter, target)
        else:
            self._draw_empty_state(painter)

        if not self._compact:
            self._draw_stream_chip(painter)
        self._draw_live_chip(painter)

        painter.setClipping(False)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(Colors.CANVAS_BORDER), 1))
        painter.drawRoundedRect(outer, self.RADIUS, self.RADIUS)

    def _draw_empty_state(self, painter: QPainter) -> None:
        rect = self.rect()
        painter.setPen(QColor(Colors.TEXT_SUBTLE))
        font = painter.font()
        icon_font = QFont(font)
        _scale_font(icon_font, 1.6 if self._compact else 2.4)
        painter.setFont(icon_font)
        icon_rect = QRect(rect.left(), rect.top(), rect.width(), rect.height() - 24)
        painter.drawText(icon_rect, Qt.AlignCenter, "◉")
        painter.setFont(font)
        painter.setPen(QColor(Colors.TEXT_MUTED))
        text_rect = QRect(
            rect.left() + 12,
            rect.center().y() + (10 if self._compact else 20),
            rect.width() - 24,
            42,
        )
        painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, self._message)

    def _draw_stream_chip(self, painter: QPainter) -> None:
        if not self._frame_label or self._pixmap is None:
            return
        text = self._frame_label
        if self._frame_size != (0, 0):
            text += f"  ·  {self._frame_size[0]}x{self._frame_size[1]}"
        if self._fps is not None and self._fps > 0:
            text += f"  ·  {self._fps:.0f} fps"
        self._draw_chip(painter, text, QColor(Colors.TEXT_MUTED), align_left=True)

    def _draw_live_chip(self, painter: QPainter) -> None:
        state = self._live_state
        if not state:
            state = "live" if self._pixmap is not None else "waiting"
        palette = {
            "live": (QColor(Colors.LIVE), "LIVE"),
            "stale": (QColor(Colors.STALE), "STALE"),
            "waiting": (QColor(Colors.TEXT_SUBTLE), "WAITING"),
            "off": (QColor(Colors.TEXT_SUBTLE), "OFF"),
        }
        color, label = palette.get(state, palette["waiting"])
        self._draw_chip(painter, label, color, align_left=False, dot=True)

    def _draw_chip(
        self,
        painter: QPainter,
        text: str,
        color: QColor,
        align_left: bool,
        dot: bool = False,
    ) -> None:
        painter.save()
        try:
            font = QFont(painter.font())
            _scale_font(font, 0.86, minimum_pt=7.0)
            font.setBold(True)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            pad_x = 9
            dot_w = 12 if dot else 0
            width = metrics.horizontalAdvance(text) + pad_x * 2 + dot_w
            height = metrics.height() + 8
            margin = 8
            x = margin if align_left else self.width() - margin - width
            rect = QRect(x, margin, width, height)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(10, 14, 19, 208))
            painter.drawRoundedRect(rect, height / 2.0, height / 2.0)
            if dot:
                dot_color = QColor(color)
                painter.setBrush(dot_color)
                cy = rect.center().y()
                painter.drawEllipse(rect.left() + pad_x - 2, cy - 3, 7, 7)
            painter.setPen(QColor(color))
            text_rect = rect.adjusted(pad_x + dot_w - (2 if dot else 0), 0, -pad_x + 2, 0)
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        finally:
            painter.restore()

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
        painter.save()
        try:
            fw, fh = self._frame_size
            gx = target.x() + (self._gaze_point[0] / max(1, fw)) * target.width()
            gy = target.y() + (self._gaze_point[1] / max(1, fh)) * target.height()
            glow = QColor(Colors.WARNING)
            glow.setAlpha(60)
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(int(gx) - 15, int(gy) - 15, 30, 30)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(Colors.WARNING), 2.4))
            painter.drawEllipse(int(gx) - 9, int(gy) - 9, 18, 18)
            painter.drawLine(int(gx) - 16, int(gy), int(gx) - 5, int(gy))
            painter.drawLine(int(gx) + 5, int(gy), int(gx) + 16, int(gy))
            painter.drawLine(int(gx), int(gy) - 16, int(gx), int(gy) - 5)
            painter.drawLine(int(gx), int(gy) + 5, int(gx), int(gy) + 16)
            painter.setBrush(QColor(Colors.WARNING))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(int(gx) - 2, int(gy) - 2, 4, 4)
        finally:
            painter.restore()

    def _draw_detection_box(self, painter: QPainter, target: QRect) -> None:
        if self._detection_bbox is None or self._frame_size == (0, 0):
            return
        fw, fh = self._frame_size
        x1, y1, x2, y2 = self._detection_bbox
        left = target.x() + (x1 / max(1, fw)) * target.width()
        top = target.y() + (y1 / max(1, fh)) * target.height()
        right = target.x() + (x2 / max(1, fw)) * target.width()
        bottom = target.y() + (y2 / max(1, fh)) * target.height()
        rect = QRect(
            int(round(left)),
            int(round(top)),
            max(1, int(round(right - left))),
            max(1, int(round(bottom - top))),
        )
        painter.save()
        try:
            glow = QColor(Colors.PRIMARY)
            glow.setAlpha(70)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(glow, 7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(QPen(QColor(Colors.PRIMARY), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawRoundedRect(rect, 6, 6)
        finally:
            painter.restore()


def _scale_font(font: QFont, factor: float, minimum_pt: float = 1.0) -> None:
    """Scale a font that may be defined in points or pixels (QSS uses px)."""
    point_size = font.pointSizeF()
    if point_size > 0:
        font.setPointSizeF(max(minimum_pt, point_size * factor))
        return
    pixel_size = font.pixelSize()
    if pixel_size > 0:
        font.setPixelSize(max(1, int(round(pixel_size * factor))))


def _array_to_qimage(arr: np.ndarray) -> QImage:
    if not isinstance(arr, np.ndarray):
        raise TypeError("frame is not a numpy array")
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"expected HxWx3 RGB frame, got {arr.shape}")
    if arr.dtype != np.uint8:
        raise ValueError(f"expected uint8 RGB frame, got {arr.dtype}")
    rgb = np.ascontiguousarray(arr)
    height, width = rgb.shape[:2]
    bytes_per_line = 3 * width
    image = QImage(rgb.data, width, height, bytes_per_line, QImage.Format_RGB888)
    return image.copy()
