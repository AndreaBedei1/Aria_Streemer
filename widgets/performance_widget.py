from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from stream_state import ConnectionSample, PerformanceSample


class PerformanceWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.title = QLabel("Performance")
        self.title.setObjectName("panelTitle")
        self.connection = QLabel("Connection: disconnected")
        self.fps = QLabel("FPS: --")
        self.drops = QLabel("Dropped: --")
        self.overwrites = QLabel("Overwrites: --")
        self.resources = QLabel("CPU/RAM: --")
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        for widget in (
            self.title,
            self.connection,
            self.fps,
            self.drops,
            self.overwrites,
            self.resources,
        ):
            layout.addWidget(widget)

    def update_sample(
        self,
        perf: PerformanceSample | None,
        conn: ConnectionSample | None,
    ) -> None:
        if conn is None:
            self.connection.setText("Connection: disconnected")
        else:
            rec = "ON" if conn.recording else "OFF"
            self.connection.setText(
                f"{conn.status_message} | {conn.mode} | REC {rec}"
            )
        if perf is None:
            self.fps.setText("FPS: --")
            self.drops.setText("Dropped: --")
            self.overwrites.setText("Overwrites: --")
            self.resources.setText("CPU/RAM: --")
            return
        self.fps.setText(
            "FPS RGB {rgb:.1f} | ET {et:.1f} | HT {ht:.1f} | BPM {bpm:.1f}".format(
                rgb=perf.fps.get("rgb", 0.0),
                et=perf.fps.get("et", 0.0),
                ht=perf.fps.get("ht", 0.0),
                bpm=perf.fps.get("bpm", 0.0),
            )
        )
        self.drops.setText(
            "Dropped RGB {rgb} | ET {et}".format(
                rgb=perf.dropped_frames.get("rgb", 0),
                et=perf.dropped_frames.get("et", 0),
            )
        )
        self.overwrites.setText(
            "Overwrite RGB {rgb} | Eye {eye} | Hand {hand}".format(
                rgb=perf.overwrite_counts.get("rgb", 0),
                eye=perf.overwrite_counts.get("eye", 0),
                hand=perf.overwrite_counts.get("hand", 0),
            )
        )
        if perf.cpu_percent is None:
            self.resources.setText("CPU/RAM: --")
        else:
            self.resources.setText(
                f"CPU {perf.cpu_percent:.0f}% | RAM {perf.ram_percent:.0f}%"
            )
