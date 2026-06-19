#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from config import AppConfig  # noqa: E402
from processing.image_conversion import assess_display_quality  # noqa: E402
from widgets.main_window import MainWindow  # noqa: E402


def qimage_to_rgb(image: QImage) -> np.ndarray:
    rgb_image = image.convertToFormat(QImage.Format_RGB888)
    width = rgb_image.width()
    height = rgb_image.height()
    arr = np.frombuffer(rgb_image.bits(), dtype=np.uint8, count=height * width * 3)
    return arr.reshape((height, width, 3)).copy()


def main() -> int:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(mock=True, rgb_fps=10, rgb_width=960, rgb_height=540)
    window = MainWindow(config)
    window.resize(1280, 820)
    window.show()

    try:
        window.worker.connect()
        window.worker.start_streaming()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()
        window._refresh()

        screenshot_path = "/tmp/aria_gui_smoke.png"
        if not window.grab().save(screenshot_path):
            print(f"FAILED: could not save {screenshot_path}")
            return 2
        canvas_path = "/tmp/aria_gui_smoke_canvas.png"
        canvas_image = window.video._canvas.grab().toImage()
        if not canvas_image.save(canvas_path):
            print(f"FAILED: could not save {canvas_path}")
            return 2

        frame = window.state.rgb_frame.get()
        if frame is None:
            print("FAILED: mock RGB frame was not produced")
            return 3
        if not frame.valid:
            print(f"FAILED: mock RGB frame invalid: {frame.warning}")
            return 4

        quality = assess_display_quality(frame.image_rgb)
        if not quality["valid"] or quality["yellow_fraction"] >= 0.55:
            print(f"FAILED: RGB panel frame looks invalid: {quality}")
            return 5
        canvas_quality = assess_display_quality(qimage_to_rgb(canvas_image))
        if not canvas_quality["valid"] or canvas_quality["yellow_fraction"] >= 0.55:
            print(f"FAILED: rendered RGB panel looks invalid: {canvas_quality}")
            return 6

        print(f"OK: saved GUI smoke screenshot to {screenshot_path}")
        return 0
    finally:
        window.worker.stop_streaming()
        window.worker.disconnect()
        window.close()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
