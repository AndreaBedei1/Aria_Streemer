from __future__ import annotations

import os
import time

import numpy as np
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from mock import mock_data_generators as gen
from processing.image_conversion import assess_display_quality, normalize_image_for_display
from stream_state import VideoFrame
from widgets.video_widget import VideoWidget


def _app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _qimage_to_rgb(image: QImage) -> np.ndarray:
    rgb_image = image.convertToFormat(QImage.Format_RGB888)
    width = rgb_image.width()
    height = rgb_image.height()
    ptr = rgb_image.bits()
    arr = np.frombuffer(ptr, dtype=np.uint8, count=height * width * 3)
    return arr.reshape((height, width, 3)).copy()


def test_video_widget_mock_screenshot_is_not_flat_yellow() -> None:
    app = _app()
    widget = VideoWidget("RGB camera live")
    widget.resize(900, 620)

    frame_arr, metadata = normalize_image_for_display(
        gen.rgb_frame(640, 480, 1.0), source_name="mock RGB"
    )
    assert metadata["valid"], metadata
    frame = VideoFrame(
        image_rgb=frame_arr,
        capture_timestamp_ns=int(time.monotonic() * 1e9),
        camera_id=64,
        label="mock RGB",
        width=frame_arr.shape[1],
        height=frame_arr.shape[0],
        metadata=metadata,
        valid=True,
        warning=str(metadata.get("warning", "")),
    )

    widget.set_frame(frame, gaze_point=(frame.width * 0.55, frame.height * 0.45))
    widget.show()
    app.processEvents()
    app.processEvents()

    screenshot = widget.grab().toImage()
    assert screenshot.save("/tmp/aria_video_widget_mock_screenshot.png")
    rgb = _qimage_to_rgb(screenshot)
    quality = assess_display_quality(rgb)

    assert float(rgb.std()) > 12.0
    assert quality["yellow_fraction"] < 0.55
    assert quality["valid"], quality
