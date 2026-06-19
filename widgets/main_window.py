from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from aria_recording_manager import AriaRecordingManager
from aria_stream_worker import AriaStreamWorker
from config import AppConfig
from mock.mock_aria_stream import MockAriaStreamWorker
from stream_state import SharedStreamState, StreamToggles
from widgets.eye_tracking_widget import EyeTrackingWidget
from widgets.hand_tracking_widget import HandTrackingWidget
from widgets.heart_rate_widget import HeartRateWidget
from widgets.performance_widget import PerformanceWidget
from widgets.physiology_widget import PhysiologyWidget
from widgets.recording_widget import RecordingWidget
from widgets.video_widget import SmallVideoWidget, VideoWidget


LOG = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self.state = SharedStreamState()
        self.recording_manager = AriaRecordingManager(config, self.state)
        if config.mock:
            self.worker = MockAriaStreamWorker(config, self.state, self.recording_manager)
        else:
            self.worker = AriaStreamWorker(config, self.state, self.recording_manager)
        self._last_lightweight_record = 0.0
        self._last_log = ""

        self.setWindowTitle("Aria Gen 2 Realtime Demo")
        self.resize(1440, 900)
        self._build_ui()
        self._apply_style()
        self._connect_signals()
        self._apply_panel_visibility(self.state.get_toggles())

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(int(1000 / max(1, config.ui_refresh_hz)))

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        top = QHBoxLayout()
        self.connect_button = QPushButton("Connect glasses")
        self.disconnect_button = QPushButton("Disconnect")
        self.start_stream_button = QPushButton("Start streaming")
        self.stop_stream_button = QPushButton("Stop streaming")
        self.reset_button = QPushButton("Reset statistics")
        for button in (
            self.connect_button,
            self.disconnect_button,
            self.start_stream_button,
            self.stop_stream_button,
            self.reset_button,
        ):
            top.addWidget(button)
        top.addStretch(1)
        root.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.video = VideoWidget("RGB camera live")
        body.addWidget(self._panel(self.video), 3)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        self.recording_widget = RecordingWidget(self.config.output_dir)
        self.heart = HeartRateWidget()
        self.eye = EyeTrackingWidget()
        self.hands = HandTrackingWidget()
        self.physio = PhysiologyWidget()
        self.performance = PerformanceWidget()
        self.et_left = SmallVideoWidget("ET left")
        self.et_right = SmallVideoWidget("ET right")
        et_row = QWidget()
        et_layout = QHBoxLayout(et_row)
        et_layout.setContentsMargins(0, 0, 0, 0)
        et_layout.addWidget(self.et_left)
        et_layout.addWidget(self.et_right)
        self.et_panel = self._panel(et_row)

        self.toggles = self._build_toggles()
        for widget in (
            self._panel(self.recording_widget),
            self._panel(self.toggles),
            self._panel(self.heart),
            self._panel(self.eye),
            self.et_panel,
            self._panel(self.hands),
            self._panel(self.physio),
            self._panel(self.performance),
        ):
            right_layout.addWidget(widget)
        right_layout.addStretch(1)
        right_scroll.setWidget(right)
        body.addWidget(right_scroll, 2)
        root.addLayout(body, 1)

        self.log_label = QLabel("Preview Mode | Waiting for data...")
        self.log_label.setObjectName("statusLine")
        root.addWidget(self.log_label)
        self.setCentralWidget(central)

    def _build_toggles(self) -> QWidget:
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(6)
        self.checkbox_map: dict[str, QCheckBox] = {}
        labels = [
            ("rgb", "RGB camera"),
            ("gaze_overlay", "Gaze overlay"),
            ("eye_tracking", "Eye tracking data"),
            ("et_cameras", "ET cameras"),
            ("pupils", "Pupils"),
            ("blink_perclos", "Blink/PERCLOS"),
            ("heart_rate", "Heart rate"),
            ("ppg_quality", "PPG quality"),
            ("pulse_variability", "Pulse variability"),
            ("hand_tracking", "Hand tracking"),
            ("als", "ALS"),
            ("temperature", "Temperature"),
            ("performance", "Performance panel"),
        ]
        defaults = vars(self.state.get_toggles())
        for i, (key, label) in enumerate(labels):
            box = QCheckBox(label)
            box.setChecked(bool(defaults[key]))
            self.checkbox_map[key] = box
            layout.addWidget(box, i // 2, i % 2)
        return widget

    def _panel(self, child: QWidget) -> QFrame:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(child)
        return frame

    def _connect_signals(self) -> None:
        self.connect_button.clicked.connect(lambda: self._run_action("Connecting", self.worker.connect))
        self.disconnect_button.clicked.connect(lambda: self._run_action("Disconnecting", self.worker.disconnect))
        self.start_stream_button.clicked.connect(
            lambda: self._run_action("Starting streaming", self.worker.start_streaming)
        )
        self.stop_stream_button.clicked.connect(
            lambda: self._run_action("Stopping streaming", self.worker.stop_streaming)
        )
        self.reset_button.clicked.connect(self.worker.reset_statistics)
        self.recording_widget.start_button.clicked.connect(
            lambda: self._run_action(
                "Starting recording",
                lambda: self.recording_manager.start_recording(
                    self.recording_widget.output_dir.text()
                ),
            )
        )
        self.recording_widget.stop_button.clicked.connect(
            lambda: self._run_action("Stopping recording", self.recording_manager.stop_recording)
        )
        for box in self.checkbox_map.values():
            box.stateChanged.connect(self._toggles_changed)

    def _toggles_changed(self) -> None:
        toggles = StreamToggles(
            **{key: box.isChecked() for key, box in self.checkbox_map.items()}
        )
        self.state.set_toggles(toggles)
        self.worker.note_toggles_changed()
        self._apply_panel_visibility(toggles)

    def _apply_panel_visibility(self, toggles: StreamToggles) -> None:
        self.et_panel.setVisible(toggles.et_cameras)
        self.heart.parentWidget().setVisible(
            toggles.heart_rate or toggles.ppg_quality or toggles.pulse_variability
        )
        self.eye.parentWidget().setVisible(
            toggles.eye_tracking or toggles.pupils or toggles.blink_perclos
        )
        self.hands.parentWidget().setVisible(toggles.hand_tracking)
        self.physio.parentWidget().setVisible(toggles.als or toggles.temperature)
        self.performance.parentWidget().setVisible(toggles.performance)

    def _run_action(self, label: str, action: Callable[[], None]) -> None:
        self.log_label.setText(label)

        def wrapped() -> None:
            try:
                action()
            except Exception as exc:
                LOG.exception("%s failed", label)
                self.state.logs.set(f"{label} failed: {exc}")

        threading.Thread(target=wrapped, name=label.lower().replace(" ", "-"), daemon=True).start()

    def _refresh(self) -> None:
        toggles = self.state.get_toggles()
        rgb = self.state.rgb_frame.get()
        eye = self.state.eye_tracking.get()
        gaze_point = eye.gaze_point_rgb if eye and toggles.gaze_overlay else None
        if toggles.rgb:
            self.video.set_frame(rgb, gaze_point, "RGB stream not available")
        else:
            self.video.set_frame(None, None, "RGB disabled")

        self.heart.update_sample(
            self.state.heart_rate.get(), self.state.pulse_variability.get()
        )
        self.eye.update_sample(eye, self.state.pupils.get())
        self.hands.update_sample(self.state.hand_tracking.get())
        self.physio.update_sample(self.state.als.get(), self.state.temperature.get())
        self.performance.update_sample(self.state.performance.get(), self.state.connection.get())
        self.recording_widget.update_state(self.state.get_recording())

        if toggles.et_cameras:
            self.et_left.set_frame(self.state.et_left_frame.get())
            self.et_right.set_frame(self.state.et_right_frame.get())

        log = self.state.logs.get()
        conn = self.state.connection.get()
        rec = self.state.get_recording()
        if rec.last_error:
            self.log_label.setText(rec.last_error)
        elif log and log != self._last_log:
            self.log_label.setText(log)
            self._last_log = log
        elif conn is not None:
            mode = "Recording Mode" if rec.active else "Preview Mode"
            self.log_label.setText(f"{mode} | {conn.status_message} | {conn.device_id}")

        self._record_lightweight_row()

    def _record_lightweight_row(self) -> None:
        rec = self.state.get_recording()
        now = time.monotonic()
        if not rec.active or now - self._last_lightweight_record < 1.0:
            return
        self._last_lightweight_record = now
        hr = self.state.heart_rate.get()
        eye = self.state.eye_tracking.get()
        pupils = self.state.pupils.get()
        hands = self.state.hand_tracking.get()
        perf = self.state.performance.get()
        pv = self.state.pulse_variability.get()
        self.recording_manager.record_lightweight_sample(
            {
                "bpm": "" if hr is None or hr.bpm is None else f"{hr.bpm:.2f}",
                "ppg_quality": "" if hr is None else hr.quality,
                "ppg_quality_score": "" if hr is None else f"{hr.quality_score:.3f}",
                "pulse_variability_rmssd_ms": ""
                if pv is None or pv.rmssd_ms is None
                else f"{pv.rmssd_ms:.2f}",
                "gaze_yaw_rad": "" if eye is None or eye.yaw_rad is None else f"{eye.yaw_rad:.5f}",
                "gaze_pitch_rad": "" if eye is None or eye.pitch_rad is None else f"{eye.pitch_rad:.5f}",
                "eye_state": "" if eye is None else eye.eye_state,
                "looking_state": "" if eye is None else eye.looking_state,
                "blink_rate_per_min": ""
                if eye is None or eye.blink_rate_per_min is None
                else f"{eye.blink_rate_per_min:.2f}",
                "perclos": "" if eye is None or eye.perclos is None else f"{eye.perclos:.3f}",
                "pupil_left_mm": ""
                if pupils is None or pupils.left_diameter_mm is None
                else f"{pupils.left_diameter_mm:.3f}",
                "pupil_right_mm": ""
                if pupils is None or pupils.right_diameter_mm is None
                else f"{pupils.right_diameter_mm:.3f}",
                "left_hand_visible": "" if hands is None else hands.left.visible,
                "right_hand_visible": "" if hands is None else hands.right.visible,
                "landmark_count": "" if hands is None else hands.landmark_count,
                "rgb_fps": "" if perf is None else f"{perf.fps.get('rgb', 0):.2f}",
                "et_fps": "" if perf is None else f"{perf.fps.get('et', 0):.2f}",
                "ht_fps": "" if perf is None else f"{perf.fps.get('ht', 0):.2f}",
                "ui_state": "recording" if rec.active else "preview",
            }
        )

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #101214;
                color: #edf2f5;
                font-family: Inter, Segoe UI, Arial, sans-serif;
                font-size: 14px;
            }
            QPushButton {
                background: #252b2f;
                color: #f4f7f8;
                border: 1px solid #3a4248;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QPushButton:hover { background: #30383d; }
            QPushButton:disabled { color: #79848d; background: #191d20; }
            QCheckBox { spacing: 8px; }
            QLineEdit {
                background: #171b1f;
                border: 1px solid #323a40;
                border-radius: 5px;
                padding: 7px;
            }
            QFrame#panel {
                background: #171b1f;
                border: 1px solid #2c343a;
                border-radius: 8px;
            }
            QLabel#panelTitle {
                color: #ffffff;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#bpmValue {
                color: #ffcf33;
                font-size: 42px;
                font-weight: 800;
            }
            QLabel#muted { color: #96a1ab; font-size: 12px; }
            QLabel#statusLine {
                color: #cdd6dd;
                background: #171b1f;
                border: 1px solid #2c343a;
                border-radius: 6px;
                padding: 8px;
            }
            QLabel#recOn {
                color: #ffffff;
                background: #b51f2a;
                border-radius: 6px;
                padding: 6px;
                font-weight: 800;
            }
            QLabel#recOff {
                color: #aeb8c2;
                background: #252b2f;
                border-radius: 6px;
                padding: 6px;
                font-weight: 700;
            }
            """
        )

    def closeEvent(self, event):  # noqa: N802
        try:
            if self.state.get_recording().active and self.config.mock:
                self.recording_manager.stop_recording()
            self.worker.stop_streaming()
            self.worker.disconnect()
        except Exception:
            LOG.exception("Error while closing app")
        event.accept()
