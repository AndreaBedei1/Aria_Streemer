from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stream_state import SharedStreamState
from widgets.theme import ICON_SIZE, icon


_PLACEHOLDER_LABELS = {"unknown", "initializing...", "stopped", "waiting for hand data"}


class ExperimentWidget(QWidget):
    """Start/stop card for the vision experiments (object / gesture)."""

    def __init__(
        self,
        output_dir: str,
        title: str = "Object Experiment",
        caption: str = "Detected Object",
        value_prefix: str = "Object",
    ):
        super().__init__()
        self.value_prefix = value_prefix
        self.title = QLabel(title.upper())
        self.title.setObjectName("panelTitle")
        self.status = QLabel("OFF")
        self.status.setObjectName("recOff")
        self.status.setMinimumWidth(46)
        self.status.setAlignment(Qt.AlignCenter)

        # Kept for API compatibility with the managers/tests.
        self.detected_object = QLabel(f"{self.value_prefix}: --")
        self.confidence = QLabel("Confidence: --")

        self.object_caption = QLabel(caption)
        self.object_caption.setObjectName("panelCaption")
        self.object_value = QLabel("--")
        self.object_value.setObjectName("objectValue")
        self.object_value.setAlignment(Qt.AlignCenter)
        self.object_value.setWordWrap(True)
        self.details = QLabel("Confidence: --")
        self.details.setObjectName("metricLabel")
        self.details.setAlignment(Qt.AlignCenter)
        self.details.setWordWrap(True)

        self.output_dir = QLineEdit(output_dir)
        self.output_dir.setVisible(False)
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.start_button.setProperty("variant", "primary")
        self.stop_button.setProperty("variant", "danger")
        self.start_button.setIcon(icon("fa5s.play", color="#06130d"))
        self.stop_button.setIcon(icon("fa5s.stop"))
        self.start_button.setIconSize(ICON_SIZE)
        self.stop_button.setIconSize(ICON_SIZE)
        self.start_button.setToolTip("Start experiment")
        self.stop_button.setToolTip("Stop experiment")
        self.start_button.setCursor(Qt.PointingHandCursor)
        self.stop_button.setCursor(Qt.PointingHandCursor)
        self.stop_button.setEnabled(False)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(self.title, 1)
        header.addWidget(self.status, 0)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(8)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        layout.addLayout(header)
        layout.addLayout(buttons)
        layout.addStretch(1)
        layout.addWidget(self.object_caption)
        layout.addWidget(self.object_value)
        layout.addWidget(self.details)

    def update_state(
        self,
        state: SharedStreamState,
        is_active: bool,
        result_attr: str = "experiment_result",
    ) -> None:
        if is_active:
            self.status.setText("ON")
            self.status.setObjectName("recOn")
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
        else:
            self.status.setText("OFF")
            self.status.setObjectName("recOff")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)

        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

        result = getattr(state, result_attr, None)
        if result:
            label = str(result.get("label", "--") or "--")
            conf = float(result.get("conf", 0.0) or 0.0)
            if label.lower() in _PLACEHOLDER_LABELS:
                display_label = "--" if not is_active else label
            else:
                display_label = label
            self.detected_object.setText(f"{self.value_prefix}: {display_label}")
            self.confidence.setText(f"Confidence: {conf:.2f}")
            self.object_value.setText(display_label)
            self.details.setText(f"Confidence: {conf:.2f}")
        else:
            self.detected_object.setText(f"{self.value_prefix}: --")
            self.confidence.setText("Confidence: --")
            self.object_value.setText("--")
            self.details.setText("Confidence: --")
