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


class ExperimentWidget(QWidget):
    def __init__(self, output_dir: str):
        super().__init__()
        self.title = QLabel("Experiment Mode")
        self.title.setObjectName("panelTitle")
        self.status = QLabel("OFF")
        self.status.setObjectName("recOff")
        self.status.setMinimumWidth(48)
        self.status.setAlignment(Qt.AlignCenter)
        
        self.detected_object = QLabel("Object: --")
        self.confidence = QLabel("Confidence: --")
        self.fps = QLabel("Inference FPS: --")
        self.object_caption = QLabel("Detected Object")
        self.object_caption.setObjectName("muted")
        self.object_value = QLabel("--")
        self.object_value.setObjectName("objectValue")
        self.object_value.setAlignment(Qt.AlignCenter)
        self.object_value.setWordWrap(True)
        self.details = QLabel("Confidence: -- | FPS: --")
        self.details.setObjectName("muted")
        self.details.setAlignment(Qt.AlignCenter)
        
        self.output_dir = QLineEdit(output_dir)
        self.output_dir.setVisible(False)
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.start_button.setProperty("variant", "primary")
        self.stop_button.setProperty("variant", "danger")
        self.start_button.setIcon(icon("fa5s.play"))
        self.stop_button.setIcon(icon("fa5s.stop"))
        self.start_button.setIconSize(ICON_SIZE)
        self.stop_button.setIconSize(ICON_SIZE)
        self.start_button.setToolTip("Start experiment")
        self.stop_button.setToolTip("Stop experiment")
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
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addLayout(buttons)
        layout.addStretch(1)
        layout.addWidget(self.object_caption)
        layout.addWidget(self.object_value)
        layout.addWidget(self.details)

    def update_state(self, state: SharedStreamState, is_active: bool) -> None:
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

        result = getattr(state, "experiment_result", None)
        if result:
            label = str(result.get("label", "--") or "--")
            conf = float(result.get("conf", 0.0) or 0.0)
            fps = float(result.get("fps", 0.0) or 0.0)
            if label.lower() in {"unknown", "initializing...", "stopped"}:
                display_label = "--" if not is_active else label
            else:
                display_label = label
            self.detected_object.setText(f"Object: {display_label}")
            self.confidence.setText(f"Confidence: {conf:.2f}")
            self.fps.setText(f"Inference FPS: {fps:.2f}")
            self.object_value.setText(display_label)
            self.details.setText(f"Confidence: {conf:.2f} | FPS: {fps:.2f}")
        else:
            self.detected_object.setText("Object: --")
            self.confidence.setText("Confidence: --")
            self.fps.setText("Inference FPS: --")
            self.object_value.setText("--")
            self.details.setText("Confidence: -- | FPS: --")
