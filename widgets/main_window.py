from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
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
from stream_state import ConnectionSample, SharedStreamState, StreamToggles
from widgets.experiment_widget import ExperimentWidget
from widgets.eye_tracking_widget import EyeTrackingWidget
from widgets.hand_tracking_widget import HandTrackingWidget
from widgets.heart_rate_widget import HeartRateWidget
from widgets.theme import (
    ICON_SIZE,
    apply_theme,
    icon,
    make_chip,
    set_chip,
    set_widget_property,
)
from widgets.video_widget import SmallVideoWidget, VideoWidget


LOG = logging.getLogger(__name__)

# A buffer older than this while streaming is flagged as stale in the UI.
STALE_AFTER_S = 2.5


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

        self._connecting = False
        self.setWindowTitle("Aria Streamer · Gen 2 Live Dashboard")
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

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addWidget(self._build_header())

        body = QSplitter(Qt.Horizontal)
        body.setChildrenCollapsible(False)

        # -------- left column: hero video + hands / eye cameras
        left_column = QWidget()
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        self.video = VideoWidget("")
        left_layout.addWidget(self._panel(self.video, role="hero"), 5)

        self.hands = HandTrackingWidget()
        self.et_left = SmallVideoWidget("LEFT")
        self.et_right = SmallVideoWidget("RIGHT")
        et_container = QWidget()
        et_layout = QVBoxLayout(et_container)
        et_layout.setContentsMargins(0, 0, 0, 0)
        et_layout.setSpacing(6)
        et_title = QLabel("EYE CAMERAS")
        et_title.setObjectName("panelTitle")
        et_layout.addWidget(et_title)
        et_row = QHBoxLayout()
        et_row.setContentsMargins(0, 0, 0, 0)
        et_row.setSpacing(8)
        et_row.addWidget(self.et_left)
        et_row.addWidget(self.et_right)
        et_layout.addLayout(et_row, 1)

        lower_row = QWidget()
        lower_row.setMinimumHeight(240)
        lower_row.setMaximumHeight(330)
        lower_layout = QHBoxLayout(lower_row)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        lower_layout.setSpacing(10)
        lower_layout.addWidget(self._panel(self.hands), 3)
        lower_layout.addWidget(self._panel(et_container), 2)
        left_layout.addWidget(lower_row, 2)

        body.addWidget(left_column)

        # -------- right column: metric cards in a scroll area
        self.heart = HeartRateWidget()
        self.eye = EyeTrackingWidget()
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

        cards = QWidget()
        cards_layout = QVBoxLayout(cards)
        cards_layout.setContentsMargins(0, 0, 4, 0)
        cards_layout.setSpacing(10)
        cards_layout.addWidget(self._panel(self.heart, min_h=280))
        cards_layout.addWidget(self._panel(self.eye))
        cards_layout.addWidget(self._panel(self.experiment_widget, min_h=190))
        cards_layout.addWidget(self._panel(self.gesture_experiment_widget, min_h=190))
        cards_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(cards)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body.addWidget(scroll)

        body.setStretchFactor(0, 7)
        body.setStretchFactor(1, 3)
        body.setSizes([1120, 460])
        root.addWidget(body, 1)

        root.addWidget(self._build_status_bar())
        self.setCentralWidget(central)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("appHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)

        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(0)
        title = QLabel("ARIA STREAMER")
        title.setObjectName("appTitle")
        subtitle = QLabel("Project Aria Gen 2 · Live Sensor Dashboard")
        subtitle.setObjectName("appSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addLayout(titles)

        layout.addSpacing(8)

        mode_text = "MOCK" if self.config.mock else self.config.connection_mode.upper()
        mode_tone = "warn" if self.config.mock else "info"
        self.mode_chip = make_chip(mode_text, tone=mode_tone)
        self.mode_chip.setToolTip("Connection mode")
        layout.addWidget(self.mode_chip)

        self.status_pill = QLabel("DISCONNECTED")
        self.status_pill.setObjectName("statusPill")
        self.status_pill.setProperty("state", "disconnected")
        layout.addWidget(self.status_pill)

        layout.addStretch(1)

        self.battery_chip = make_chip("", tone="")
        self.battery_chip.setToolTip("Glasses battery")
        self.battery_chip.setVisible(False)
        self.wifi_chip = make_chip("", tone="info")
        self.wifi_chip.setToolTip("Glasses Wi-Fi network / IP")
        self.wifi_chip.setVisible(False)
        self.temp_chip = make_chip("", tone="")
        self.temp_chip.setToolTip("Device temperature")
        self.temp_chip.setVisible(False)
        for chip in (self.battery_chip, self.wifi_chip, self.temp_chip):
            layout.addWidget(chip)

        layout.addSpacing(6)

        self.connect_button = QPushButton("Start Streaming")
        self.stop_stream_button = QPushButton("Stop")
        self._configure_button(
            self.connect_button, "fa5s.play", "primary", "Connect the glasses and start streaming"
        )
        self._configure_button(
            self.stop_stream_button, "fa5s.stop", "danger", "Stop streaming (and experiments)"
        )
        self.stop_stream_button.setEnabled(False)
        layout.addWidget(self.connect_button)
        layout.addWidget(self.stop_stream_button)
        return header

    def _build_status_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("statusBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)
        self.status_detail = QLabel("Ready.")
        self.status_detail.setObjectName("statusDetail")
        self.status_log = QLabel("")
        self.status_log.setObjectName("statusLog")
        self.status_log.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.status_detail, 3)
        layout.addWidget(self.status_log, 2)
        return bar

    def _panel(self, child: QWidget, role: str = "default", min_h: int = 0) -> QFrame:
        frame = QFrame()
        frame.setObjectName("panel")
        frame.setProperty("role", role)
        if min_h:
            frame.setMinimumHeight(min_h)
            frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout = QVBoxLayout(frame)
        margin = 12
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.addWidget(child)
        return frame

    def _configure_button(
        self, button: QPushButton, icon_name: str, variant: str, tooltip: str
    ) -> None:
        button.setProperty("variant", variant)
        icon_color = "#06130d" if variant == "primary" else None
        button.setIcon(icon(icon_name, color=icon_color) if icon_color else icon(icon_name))
        button.setIconSize(ICON_SIZE)
        button.setToolTip(tooltip)
        button.setCursor(Qt.PointingHandCursor)

    # ------------------------------------------------------------- signals

    def _connect_signals(self) -> None:
        self.connect_button.clicked.connect(self._on_start_clicked)
        self.stop_stream_button.clicked.connect(
            lambda: self._run_action("Stopping all", self._stop_all)
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
            lambda: self._run_action(
                "Stopping gesture experiment", self.gesture_experiment_manager.stop_experiment
            )
        )

    def _on_start_clicked(self) -> None:
        self._connecting = True
        self.connect_button.setEnabled(False)
        self._run_action("Starting stream", self._connect_and_stream)

    def _run_action(self, label: str, action: Callable[[], None]) -> None:
        def wrapped() -> None:
            try:
                action()
            except Exception as exc:
                LOG.exception("%s failed", label)
                self.state.logs.set(f"{label} failed: {exc}")
            finally:
                if label == "Starting stream":
                    self._connecting = False

        threading.Thread(target=wrapped, name=label.lower().replace(" ", "-"), daemon=True).start()

    def _connect_and_stream(self) -> None:
        self.worker.connect()
        self.worker.start_streaming()

    def _stop_all(self) -> None:
        self.experiment_manager.stop_experiment()
        self.gesture_experiment_manager.stop_experiment()
        self.worker.stop_streaming()

    # ------------------------------------------------------------- refresh

    def _refresh(self) -> None:
        connection = self.state.connection.get()
        streaming = bool(connection.streaming) if connection else False

        rgb_snapshot = self.state.rgb_frame.snapshot()
        rgb = rgb_snapshot.value
        rgb_age = rgb_snapshot.age_s

        eye_snapshot = self.state.eye_tracking.snapshot()
        eye = eye_snapshot.value
        gaze_point = eye.gaze_point_rgb if eye else None

        result = getattr(self.state, "experiment_result", {}) or {}
        gesture_result = getattr(self.state, "gesture_experiment_result", {}) or {}
        bbox = None
        if self.experiment_manager.is_active:
            bbox = result.get("bbox")
        elif self.gesture_experiment_manager.is_active:
            bbox = gesture_result.get("bbox")

        perf = self.state.performance.get()
        rgb_fps = perf.fps.get("rgb") if perf else None
        self.video.set_frame(
            rgb,
            gaze_point,
            self._video_message(streaming),
            bbox,
            live_state=self._live_state(streaming, rgb is not None, rgb_age),
            fps=rgb_fps,
        )

        self.heart.update_sample(
            self.state.heart_rate.get(), self.state.pulse_variability.get()
        )
        self.eye.update_sample(
            eye,
            self.state.pupils.get(),
            stale=self._is_stale(streaming, eye is not None, eye_snapshot.age_s),
        )
        hands_snapshot = self.state.hand_tracking.snapshot()
        self.hands.update_sample(
            hands_snapshot.value,
            stale=self._is_stale(streaming, hands_snapshot.value is not None, hands_snapshot.age_s),
        )
        self.experiment_widget.update_state(self.state, self.experiment_manager.is_active)
        self.gesture_experiment_widget.update_state(
            self.state,
            self.gesture_experiment_manager.is_active,
            "gesture_experiment_result",
        )

        left_snapshot = self.state.et_left_frame.snapshot()
        right_snapshot = self.state.et_right_frame.snapshot()
        self.et_left.set_frame(
            left_snapshot.value,
            "No signal",
            live_state=self._live_state(streaming, left_snapshot.value is not None, left_snapshot.age_s),
        )
        self.et_right.set_frame(
            right_snapshot.value,
            "No signal",
            live_state=self._live_state(streaming, right_snapshot.value is not None, right_snapshot.age_s),
        )

        self._refresh_header(connection)
        self._refresh_status_bar(connection)

    def _video_message(self, streaming: bool) -> str:
        if self.config.mock:
            return "Mock stream stopped" if not streaming else "Waiting for mock frames..."
        if not streaming:
            return "Press Start Streaming to begin"
        return "Streaming active — waiting for real camera frames..."

    @staticmethod
    def _is_stale(streaming: bool, has_value: bool, age_s: Optional[float]) -> bool:
        return bool(streaming and has_value and age_s is not None and age_s > STALE_AFTER_S)

    def _live_state(self, streaming: bool, has_value: bool, age_s: Optional[float]) -> str:
        if not has_value:
            return "waiting" if streaming else "off"
        if self._is_stale(streaming, has_value, age_s):
            return "stale"
        if not streaming:
            return "off"
        return "live"

    def _refresh_header(self, connection: Optional[ConnectionSample]) -> None:
        state, text = self._pill_state(connection)
        self.status_pill.setText(text)
        set_widget_property(self.status_pill, "state", state)

        streaming = bool(connection.streaming) if connection else False
        self.connect_button.setEnabled(not streaming and not self._connecting)
        self.stop_stream_button.setEnabled(streaming or self._connecting)

        if connection is not None and connection.battery_percent is not None:
            charge = "⚡ " if connection.charging else ""
            level = connection.battery_percent
            tone = "good" if level >= 40 else ("warn" if level >= 15 else "danger")
            set_chip(self.battery_chip, f"{charge}{level}%", tone)
            self.battery_chip.setVisible(True)
        else:
            self.battery_chip.setVisible(False)

        wifi_text = ""
        if connection is not None:
            wifi_text = connection.wifi_ssid or connection.device_ip
        if wifi_text:
            set_chip(self.wifi_chip, wifi_text, "info")
            self.wifi_chip.setVisible(True)
        else:
            self.wifi_chip.setVisible(False)

        temp_snapshot = self.state.temperature.snapshot()
        temperature = temp_snapshot.value
        temp_fresh = temp_snapshot.age_s is not None and temp_snapshot.age_s < 30.0
        if (
            temperature is not None
            and temperature.temperature_c is not None
            and (temp_fresh or self.config.mock)
        ):
            tone = "danger" if temperature.warning else ""
            set_chip(self.temp_chip, f"{temperature.temperature_c:.1f}°C", tone)
            self.temp_chip.setVisible(True)
        else:
            # No fresh reading (e.g. control channel lost): hide instead of
            # showing a stale value as if it were live.
            self.temp_chip.setVisible(False)

    def _pill_state(self, connection: Optional[ConnectionSample]) -> tuple[str, str]:
        if connection is None:
            if self._connecting:
                return "connecting", "CONNECTING…"
            return "disconnected", "DISCONNECTED"
        if connection.streaming:
            if not connection.control_alive:
                return "degraded", "STREAMING · NO CONTROL"
            if connection.publishing is False:
                return "degraded", "STREAMING · NO DATA"
            return "streaming", "STREAMING"
        if self._connecting:
            return "connecting", "CONNECTING…"
        if connection.connected:
            if not connection.control_alive:
                return "degraded", "CONTROL LOST"
            return "connected", "CONNECTED"
        return "disconnected", "DISCONNECTED"

    def _refresh_status_bar(self, connection: Optional[ConnectionSample]) -> None:
        if connection is None:
            detail = "Ready. Press Start Streaming to connect the glasses."
        else:
            parts = []
            if connection.device_id:
                parts.append(connection.device_id)
            if connection.profile_name:
                parts.append(f"profile {connection.profile_name}")
            if connection.streaming_interface:
                parts.append(connection.streaming_interface)
            if connection.batch_period_ms is not None and not self.config.mock:
                parts.append(f"batch {connection.batch_period_ms} ms")
            if connection.endpoint_url:
                parts.append(f"→ {connection.endpoint_url}")
            elif connection.mode == "wifi" and connection.streaming:
                parts.append("→ mDNS oatmeal_server.local")
            if connection.publishing is not None:
                rx = connection.publisher_ip or ("yes" if connection.publishing else "no")
                parts.append(f"RX {rx if connection.publishing else '—'}")
            if connection.sdk_version and connection.sdk_version != "unknown":
                parts.append(f"SDK {connection.sdk_version}")
            detail = "  ·  ".join(parts) if parts else connection.status_message
        self.status_detail.setText(detail)

        log_message = self.state.logs.get() or ""
        self.status_log.setText(log_message)

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
