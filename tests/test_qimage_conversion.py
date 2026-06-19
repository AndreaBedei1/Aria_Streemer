from __future__ import annotations

import numpy as np

from mock import mock_data_generators as gen
from widgets.video_widget import _array_to_qimage


def test_array_to_qimage_converts_mock_frame() -> None:
    frame = gen.rgb_frame(320, 180, 0.75)
    image = _array_to_qimage(frame)

    assert not image.isNull()
    assert image.width() == 320
    assert image.height() == 180
    assert image.save("/tmp/aria_qimage_conversion.png")


def test_array_to_qimage_rejects_invalid_frames() -> None:
    with np.testing.assert_raises(ValueError):
        _array_to_qimage(np.zeros((40, 40), dtype=np.uint8))
    with np.testing.assert_raises(ValueError):
        _array_to_qimage(np.zeros((40, 40, 3), dtype=np.float32))
