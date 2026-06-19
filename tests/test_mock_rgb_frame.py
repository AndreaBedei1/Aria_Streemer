from __future__ import annotations

import numpy as np

from mock import mock_data_generators as gen
from processing.image_conversion import normalize_image_for_display


def test_mock_rgb_frame_is_not_solid_yellow() -> None:
    frame = gen.rgb_frame(960, 540, 1.25)
    assert frame.shape == (540, 960, 3)
    assert frame.dtype == np.uint8
    assert float(frame.std()) > 20.0

    rgb, metadata = normalize_image_for_display(frame, source_name="mock RGB")
    assert metadata["valid"], metadata
    assert metadata["conversion_path"] == "as_rgb"
    assert metadata["yellow_fraction"] < 0.55

    try:
        import cv2

        cv2.imwrite("/tmp/aria_mock_rgb_frame.png", rgb[:, :, ::-1])
    except Exception:
        from PIL import Image

        Image.fromarray(rgb).save("/tmp/aria_mock_rgb_frame.png")
