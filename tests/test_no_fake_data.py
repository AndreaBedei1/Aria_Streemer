"""Real mode must never invent values: N/A or waiting states instead.

These tests pin the UI behaviour when no real sample (or no fresh sample) is
available, and that live device readings disappear instead of freezing when
the control channel is lost.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from processing.ppg_hr import PpgHeartRateEstimator  # noqa: E402
from stream_state import EyeTrackingSample, PupilSample  # noqa: E402
from widgets.eye_tracking_widget import EyeTrackingWidget  # noqa: E402
from widgets.heart_rate_widget import HeartRateWidget  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_ppg_estimator_reports_no_bpm_without_data() -> None:
    estimate = PpgHeartRateEstimator().estimate()
    assert estimate.bpm is None
    assert "Not enough PPG data" in estimate.message


def test_heart_widget_shows_waiting_without_real_ppg() -> None:
    _app()
    widget = HeartRateWidget()
    widget.update_sample(None, None)
    assert widget.bpm.text() == "--"
    assert "Waiting for real PPG data" in widget.quality.text()
    assert "N/A" in widget.variability.text()


def test_eye_widget_shows_na_without_real_gaze() -> None:
    _app()
    widget = EyeTrackingWidget()
    widget.update_sample(None, None)
    for key in ("looking", "gaze", "depth", "blink", "perclos"):
        assert widget._rows[key].text() == "N/A", key
    # Pupil diameter is not exposed by the live Gen 2 EyeGaze callback.
    assert "not in live SDK" in widget._rows["pupils"].text()


def test_eye_widget_keeps_pupils_na_with_note_only_sample() -> None:
    _app()
    widget = EyeTrackingWidget()
    sample = EyeTrackingSample(timestamp_s=time.monotonic(), yaw_rad=0.1, pitch_rad=-0.05)
    pupil = PupilSample(timestamp_s=time.monotonic(), note="not exposed")
    widget.update_sample(sample, pupil)
    assert "not in live SDK" in widget._rows["pupils"].text()
    # Depth was not provided: shown as N/A, not invented.
    assert widget._rows["depth"].text() == "N/A"


def test_battery_hidden_when_control_channel_lost(monkeypatch) -> None:
    from tests.test_stream_worker_wifi import FakeDevice, FakeStatus, make_worker

    device = FakeDevice(FakeStatus(wifi_connected=True))
    worker, state = make_worker(monkeypatch, "wifi", device)
    worker.connect()
    worker.start_streaming()

    sample = state.connection.get()
    assert sample.battery_percent == 87

    for _ in range(3):
        worker._note_control_result(False)
    worker._update_connection(worker._connection_state_label())
    sample = state.connection.get()
    assert sample.battery_percent is None
    assert sample.charging is None
    assert sample.control_alive is False
