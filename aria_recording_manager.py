from __future__ import annotations

import csv
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from config import AppConfig
from stream_state import SharedStreamState


LOG = logging.getLogger(__name__)


class AriaRecordingManager:
    def __init__(self, config: AppConfig, state: SharedStreamState):
        self.config = config
        self.state = state
        self._device: Any = None
        self._sdk_gen2: Any = None
        self._lock = threading.Lock()
        self._csv_file = None
        self._csv_writer: Optional[csv.DictWriter] = None

    def set_device(self, device: Any, sdk_gen2: Any) -> None:
        with self._lock:
            self._device = device
            self._sdk_gen2 = sdk_gen2

    def clear_device(self) -> None:
        with self._lock:
            self._device = None
            self._sdk_gen2 = None

    def start_recording(self, output_dir: str | None = None) -> None:
        with self._lock:
            if self.state.get_recording().active or self.state.get_recording().starting:
                return
            device = self._device
            sdk_gen2 = self._sdk_gen2
            if (device is None or sdk_gen2 is None) and not self.config.mock:
                self.state.update_recording(last_error="Device not connected")
                return
            self.state.update_recording(starting=True, last_error="")

        session_name = datetime.now().strftime("aria_demo_%Y%m%d_%H%M%S")
        out_dir = Path(output_dir or self.config.output_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        local_csv_path = out_dir / f"{session_name}_lightweight.csv"

        try:
            uuid = ""
            device_side = not self.config.mock
            if device_side:
                recording_config = sdk_gen2.RecordingConfig()
                recording_config.recording_name = session_name
                recording_config.profile_name = self.config.recording_profile
                device.set_recording_config(recording_config)
                uuid = device.start_recording()
            self._open_csv(local_csv_path)
            self.state.update_recording(
                active=True,
                starting=False,
                stopping=False,
                session_name=session_name,
                output_dir=str(out_dir),
                uuid=str(uuid),
                started_at=time.monotonic(),
                local_csv_path=str(local_csv_path),
                last_error="",
                device_side=device_side,
            )
            LOG.info("Started recording %s uuid=%s device_side=%s", session_name, uuid, device_side)
        except Exception as exc:
            LOG.exception("Failed to start recording")
            self._close_csv()
            self.state.update_recording(
                active=False,
                starting=False,
                stopping=False,
                last_error=f"Start recording failed: {exc}",
            )

    def stop_recording(self) -> None:
        with self._lock:
            rec = self.state.get_recording()
            if not rec.active or rec.stopping:
                return
            device = self._device
            self.state.update_recording(stopping=True, last_error="")

        try:
            if device is not None and not self.config.mock:
                device.stop_recording()
            LOG.info("Stopped device-side recording")
        except Exception as exc:
            LOG.exception("Failed to stop recording")
            self.state.update_recording(last_error=f"Stop recording failed: {exc}")
        finally:
            self._close_csv()
            self.state.update_recording(active=False, stopping=False, starting=False)

    def record_lightweight_sample(self, row: Dict[str, Any]) -> None:
        rec = self.state.get_recording()
        if not rec.active:
            return
        with self._lock:
            if self._csv_writer is None:
                return
            safe_row = {
                "monotonic_s": f"{time.monotonic():.3f}",
                "session": rec.session_name,
                **row,
            }
            self._csv_writer.writerow(safe_row)
            if self._csv_file is not None:
                self._csv_file.flush()

    def _open_csv(self, path: Path) -> None:
        self._close_csv()
        fieldnames = [
            "monotonic_s",
            "session",
            "bpm",
            "ppg_quality",
            "ppg_quality_score",
            "pulse_variability_rmssd_ms",
            "gaze_yaw_rad",
            "gaze_pitch_rad",
            "eye_state",
            "looking_state",
            "blink_rate_per_min",
            "perclos",
            "pupil_left_mm",
            "pupil_right_mm",
            "left_hand_visible",
            "right_hand_visible",
            "landmark_count",
            "rgb_fps",
            "et_fps",
            "ht_fps",
            "ui_state",
        ]
        self._csv_file = path.open("w", newline="", encoding="utf-8")
        self._csv_writer = csv.DictWriter(
            self._csv_file, fieldnames=fieldnames, extrasaction="ignore"
        )
        self._csv_writer.writeheader()

    def _close_csv(self) -> None:
        with self._lock:
            if self._csv_file is not None:
                try:
                    self._csv_file.close()
                except Exception:
                    LOG.exception("Failed to close lightweight recording CSV")
            self._csv_file = None
            self._csv_writer = None
