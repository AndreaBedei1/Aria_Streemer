from __future__ import annotations

import logging
import threading
from typing import Callable

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from aria_stream_worker import AriaStreamWorker
from config import AppConfig
from experiment_manager import ExperimentManager
from gesture_experiment_manager import GestureExperimentManager
from mock.mock_aria_stream import MockAriaStreamWorker
from stream_state import SharedStreamState, StreamToggles
from widgets.hand_tracking_widget import HandTrackingWidget
from widgets.heart_rate_widget import HeartRateWidget
from widgets.theme import ICON_SIZE, add_card_shadow, apply_theme, icon
from widgets.experiment_widget import ExperimentWidget
from widgets.video_widget import SmallVideoWidget, VideoWidget


LOG = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self.state = SharedStreamState()
        self._force_all_streams()
        self.experiment_manager = ExperimentManager(config, self.state)
        self.gesture_experiment_manager = GestureExperimentManager(config, self.state)
        if config.mock:
            self.worker = MockAriaStreamWorker(config, self.state)
        else:
            self.worker = AriaStreamWorker(config, self.state)

        self.setWindowTitle("Aria Streamer")
        self.resize(1600, 950)
        self.setMinimumSize(1180, 720)
        self._build_ui()
        self._apply_style()
        self._connect_signals()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(int(1000 / max(1, config.ui_refresh_hz)))

    def _force_all_streams(self) -> None:
        self.state.set_toggles(
            StreamToggles(
                rgb=True,
                gaze_overlay=True,
                eye_tracking=True,
                et_cameras=True,
                pupils=True,
                blink_perclos=True,
                heart_rate=True,
                ppg_quality=True,
                pulse_variability=True,
                hand_tracking=True,
                als=True,
                temperature=True,
                performance=True,
            )
        )

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addWidget(self._build_header())

        body = QSplitter(Qt.Horizontal)
        body.setChildrenCollapsible(False)
        left_column = QWidget()
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        self.video = VideoWidget("")
        left_layout.addWidget(self._panel(self.video, role="hero"), 5)

        self.hands = HandTrackingWidget()
        self.et_left = SmallVideoWidget("")
        self.et_right = SmallVideoWidget("")
        et_row = QWidget()
        et_layout = QHBoxLayout(et_row)
        et_layout.setContentsMargins(0, 0, 0, 0)
        et_layout.setSpacing(6)
        et_layout.addWidget(self.et_left)
        et_layout.addWidget(self.et_right)

        lower_row = QWidget()
        lower_row.setMinimumHeight(260)
        lower_row.setMaximumHeight(340)
        lower_layout = QHBoxLayout(lower_row)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        lower_layout.setSpacing(10)
        lower_layout.addWidget(self._panel(self.hands, role="handsLarge"), 3)
        lower_layout.addWidget(self._panel(et_row, role="eyesCompact"), 2)
        left_layout.addWidget(lower_row, 2)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        self.experiment_widget = ExperimentWidget(
            self.config.output_dir,
            title="Object Experiment",
            caption="Detected Object",
            value_prefix="Object",
        )
        self.gesture_experiment_widget = ExperimentWidget(
            self.config.output_dir,
            title="Gesture Experiment",
            caption="Detected Gesture",
            value_prefix="Gesture",
        )
        self.heart = HeartRateWidget()
        body.addWidget(left_column)

        right_layout.addWidget(self._panel(self.heart, role="heart"))
        right_layout.addWidget(self._panel(self.experiment_widget, role="experiment"))
        right_layout.addWidget(self._panel(self.gesture_experiment_widget, role="experiment"))
        right_layout.addStretch(1)
        body.addWidget(right)
        body.setStretchFactor(0, 7)
        body.setStretchFactor(1, 3)
        body.setSizes([1080, 480])
        root.addWidget(body, 1)
        self.setCentralWidget(central)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("appHeader")
        add_card_shadow(header)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(16)

        title = QLabel("Aria Streamer")
        title.setObjectName("appTitle")
        layout.addWidget(title, 1)

        command_bar = QFrame()
        command_bar.setObjectName("commandBar")
        commands = QHBoxLayout(command_bar)
        commands.setContentsMargins(0, 0, 0, 0)
        commands.setSpacing(8)

        self.connect_button = QPushButton("Connect Stream")
        self.stop_stream_button = QPushButton("Stop")
        self._configure_button(self.connect_button, "fa5s.play", "primary", "Connect and start streaming")
        self._configure_button(self.stop_stream_button, "fa5s.stop", "danger", "Stop streaming")
        for button in (
            self.connect_button,
            self.stop_stream_button,
        ):
            commands.addWidget(button)
        layout.addWidget(command_bar)
        return header

    def _panel(self, child: QWidget, role: str = "default") -> QFrame:
        frame = QFrame()
        frame.setObjectName("panel")
        frame.setProperty("role", role)
        if role == "compact":
            frame.setMinimumHeight(112)
            frame.setMaximumHeight(128)
        elif role == "heart":
            frame.setMinimumHeight(270)
            frame.setMaximumHeight(320)
        elif role == "experiment":
            frame.setMinimumHeight(185)
            frame.setMaximumHeight(220)
        elif role == "handsLarge":
            frame.setMinimumHeight(250)
        elif role == "eyesCompact":
            frame.setMinimumHeight(250)
        if role in {"compact", "heart", "experiment"}:
            frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        add_card_shadow(frame)
        layout = QVBoxLayout(frame)
        margin = 10 if role in {"compact", "handsLarge", "eyesCompact"} else 12
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.addWidget(child)
        return frame

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def _configure_button(self, button: QPushButton, icon_name: str, variant: str, tooltip: str) -> None:
        button.setProperty("variant", variant)
        button.setIcon(icon(icon_name))
        button.setIconSize(ICON_SIZE)
        button.setToolTip(tooltip)
        button.setCursor(Qt.PointingHandCursor)

    def _connect_signals(self) -> None:
        self.connect_button.clicked.connect(lambda: self._run_action("Starting stream", self._connect_and_stream))
        self.stop_stream_button.clicked.connect(
            lambda: self._run_action("Stopping streaming", self.worker.stop_streaming)
        )
        self.experiment_widget.start_button.clicked.connect(
            lambda: self._run_action(
                "Starting experiment",
                lambda: self.experiment_manager.start_experiment(
                    self.experiment_widget.output_dir.text()
                ),
            )
        )
        self.experiment_widget.stop_button.clicked.connect(
            lambda: self._run_action("Stopping experiment", self.experiment_manager.stop_experiment)
        )
        self.gesture_experiment_widget.start_button.clicked.connect(
            lambda: self._run_action(
                "Starting gesture experiment",
                lambda: self.gesture_experiment_manager.start_experiment(
                    self.gesture_experiment_widget.output_dir.text()
                ),
            )
        )
        self.gesture_experiment_widget.stop_button.clicked.connect(
            lambda: self._run_action("Stopping gesture experiment", self.gesture_experiment_manager.stop_experiment)
        )

    def _run_action(self, label: str, action: Callable[[], None]) -> None:
        def wrapped() -> None:
            try:
                action()
            except Exception as exc:
                LOG.exception("%s failed", label)
                self.state.logs.set(f"{label} failed: {exc}")

        threading.Thread(target=wrapped, name=label.lower().replace(" ", "-"), daemon=True).start()

    def _refresh(self) -> None:
        rgb = self.state.rgb_frame.get()
        eye = self.state.eye_tracking.get()
        gaze_point = eye.gaze_point_rgb if eye else None
        result = getattr(self.state, "experiment_result", {}) or {}
        gesture_result = getattr(self.state, "gesture_experiment_result", {}) or {}
        bbox = None
        if self.experiment_manager.is_active:
            bbox = result.get("bbox")
        elif self.gesture_experiment_manager.is_active:
            bbox = gesture_result.get("bbox")
        self.video.set_frame(rgb, gaze_point, "Camera preview not available", bbox)

        self.heart.update_sample(
            self.state.heart_rate.get(), self.state.pulse_variability.get()
        )
        self.hands.update_sample(self.state.hand_tracking.get())
        self.experiment_widget.update_state(self.state, self.experiment_manager.is_active)
        self.gesture_experiment_widget.update_state(
            self.state,
            self.gesture_experiment_manager.is_active,
            "gesture_experiment_result",
        )

        self.et_left.set_frame(self.state.et_left_frame.get())
        self.et_right.set_frame(self.state.et_right_frame.get())

    def _connect_and_stream(self) -> None:
        self.worker.connect()
        self.worker.start_streaming()

    def _apply_style(self) -> None:
        apply_theme(QApplication.instance() or self)

    def closeEvent(self, event):  # noqa: N802
        try:
            self.worker.stop_streaming()
            self.worker.disconnect()
            self.experiment_manager.close()
            self.gesture_experiment_manager.close()
        except Exception:
            LOG.exception("Error while closing app")
        event.accept()
