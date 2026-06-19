from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stream_state import RecordingState


class RecordingWidget(QWidget):
    def __init__(self, output_dir: str):
        super().__init__()
        self.title = QLabel("Recording")
        self.title.setObjectName("panelTitle")
        self.rec = QLabel("REC OFF")
        self.rec.setObjectName("recOff")
        self.timer = QLabel("00:00")
        self.session = QLabel("Session: --")
        self.output_dir = QLineEdit(output_dir)
        self.start_button = QPushButton("Start Recording")
        self.stop_button = QPushButton("Stop Recording")
        self.stop_button.setEnabled(False)

        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.addWidget(self.title)
        layout.addWidget(self.rec)
        layout.addWidget(self.timer)
        layout.addWidget(self.session)
        layout.addWidget(self.output_dir)
        layout.addLayout(buttons)

    def update_state(self, state: RecordingState) -> None:
        active = state.active or state.starting or state.stopping
        if state.active:
            self.rec.setText("REC")
            self.rec.setObjectName("recOn")
        elif state.starting:
            self.rec.setText("REC STARTING")
            self.rec.setObjectName("recOn")
        elif state.stopping:
            self.rec.setText("REC STOPPING")
            self.rec.setObjectName("recOn")
        else:
            self.rec.setText("REC OFF")
            self.rec.setObjectName("recOff")
        self.rec.style().unpolish(self.rec)
        self.rec.style().polish(self.rec)

        elapsed = int(state.elapsed_s)
        self.timer.setText(f"{elapsed // 60:02d}:{elapsed % 60:02d}")
        self.session.setText(f"Session: {state.session_name or '--'}")
        self.start_button.setEnabled(not active)
        self.stop_button.setEnabled(state.active and not state.stopping)
