from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stream_state import SharedStreamState


class ExperimentWidget(QWidget):
    def __init__(self, output_dir: str):
        super().__init__()
        self.title = QLabel("Experiment Mode")
        self.title.setObjectName("panelTitle")
        self.status = QLabel("OFF")
        self.status.setObjectName("recOff")
        
        self.detected_object = QLabel("Object: --")
        self.confidence = QLabel("Confidence: --")
        self.fps = QLabel("Inference FPS: --")
        
        self.output_dir = QLineEdit(output_dir)
        self.start_button = QPushButton("Inizia esperimento")
        self.stop_button = QPushButton("Ferma esperimento")
        self.stop_button.setEnabled(False)

        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.addWidget(self.title)
        layout.addWidget(self.status)
        layout.addWidget(self.detected_object)
        layout.addWidget(self.confidence)
        layout.addWidget(self.fps)
        layout.addWidget(self.output_dir)
        layout.addLayout(buttons)

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
            self.detected_object.setText(f"Object: {result.get('label', '--')}")
            self.confidence.setText(f"Confidence: {result.get('conf', 0.0):.2f}")
            self.fps.setText(f"Inference FPS: {result.get('fps', 0.0):.2f}")
        else:
            self.detected_object.setText("Object: --")
            self.confidence.setText("Confidence: --")
            self.fps.setText("Inference FPS: --")
