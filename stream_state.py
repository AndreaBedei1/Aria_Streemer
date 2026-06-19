from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from latest_buffer import LatestValueBuffer


Point2D = Tuple[float, float]
Point3D = Tuple[float, float, float]


@dataclass
class VideoFrame:
    image_rgb: np.ndarray
    capture_timestamp_ns: int
    camera_id: int
    label: str
    width: int
    height: int


@dataclass
class EyeTrackingSample:
    timestamp_s: float
    yaw_rad: Optional[float] = None
    pitch_rad: Optional[float] = None
    depth_m: Optional[float] = None
    combined_gaze_valid: Optional[bool] = None
    gaze_point_rgb: Optional[Point2D] = None
    eye_state: str = "Waiting for data..."
    looking_state: str = "Waiting for data..."
    blink_rate_per_min: Optional[float] = None
    perclos: Optional[float] = None


@dataclass
class PupilSample:
    timestamp_s: float
    left_center: Optional[Point2D] = None
    right_center: Optional[Point2D] = None
    left_diameter_mm: Optional[float] = None
    right_diameter_mm: Optional[float] = None
    ambient_lux: Optional[float] = None
    note: str = "Pupil data not available"


@dataclass
class PpgSample:
    timestamp_s: float
    value: float
    capture_timestamp_ns: int = 0


@dataclass
class HeartRateSample:
    timestamp_s: float
    bpm: Optional[float]
    quality: str
    quality_score: float
    trend: str
    source: str = "PPG"
    message: str = ""
    ppg_plot: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class PulseVariabilitySample:
    timestamp_s: float
    rmssd_ms: Optional[float]
    status: str
    peak_count: int = 0


@dataclass
class AmbientLightSample:
    timestamp_s: float
    lux: Optional[float]
    state: str
    message: str = ""


@dataclass
class TemperatureSample:
    timestamp_s: float
    temperature_c: Optional[float]
    sensor_name: str = "device"
    warning: bool = False
    message: str = ""


@dataclass
class HandSideSample:
    visible: bool
    confidence: Optional[float] = None
    landmarks_device: List[Point3D] = field(default_factory=list)
    wrist_device: Optional[Point3D] = None
    palm_device: Optional[Point3D] = None


@dataclass
class HandTrackingSample:
    timestamp_s: float
    left: HandSideSample = field(default_factory=lambda: HandSideSample(False))
    right: HandSideSample = field(default_factory=lambda: HandSideSample(False))
    message: str = "Hand tracking not available"

    @property
    def landmark_count(self) -> int:
        return len(self.left.landmarks_device) + len(self.right.landmarks_device)


@dataclass
class ConnectionSample:
    timestamp_s: float
    connected: bool
    streaming: bool
    recording: bool
    mode: str
    device_id: str = ""
    device_ip: str = ""
    sdk_version: str = "unknown"
    status_message: str = "Disconnected"
    profile_name: str = ""


@dataclass
class PerformanceSample:
    timestamp_s: float
    fps: Dict[str, float] = field(default_factory=dict)
    dropped_frames: Dict[str, int] = field(default_factory=dict)
    overwrite_counts: Dict[str, int] = field(default_factory=dict)
    cpu_percent: Optional[float] = None
    ram_percent: Optional[float] = None
    connection_state: str = "Disconnected"
    recording_state: str = "OFF"


@dataclass
class RecordingState:
    active: bool = False
    starting: bool = False
    stopping: bool = False
    session_name: str = ""
    output_dir: str = ""
    uuid: str = ""
    started_at: float = 0.0
    last_error: str = ""
    local_csv_path: str = ""
    device_side: bool = True

    @property
    def elapsed_s(self) -> float:
        if not self.active or self.started_at <= 0:
            return 0.0
        return max(0.0, time.monotonic() - self.started_at)


@dataclass
class StreamToggles:
    rgb: bool = True
    gaze_overlay: bool = True
    eye_tracking: bool = True
    et_cameras: bool = False
    pupils: bool = True
    blink_perclos: bool = True
    heart_rate: bool = True
    ppg_quality: bool = True
    pulse_variability: bool = True
    hand_tracking: bool = True
    als: bool = True
    temperature: bool = True
    performance: bool = True


class SharedStreamState:
    def __init__(self) -> None:
        self.rgb_frame = LatestValueBuffer[VideoFrame]("rgb")
        self.et_left_frame = LatestValueBuffer[VideoFrame]("et_left")
        self.et_right_frame = LatestValueBuffer[VideoFrame]("et_right")
        self.eye_tracking = LatestValueBuffer[EyeTrackingSample]("eye_tracking")
        self.pupils = LatestValueBuffer[PupilSample]("pupils")
        self.heart_rate = LatestValueBuffer[HeartRateSample]("heart_rate")
        self.pulse_variability = LatestValueBuffer[PulseVariabilitySample](
            "pulse_variability"
        )
        self.als = LatestValueBuffer[AmbientLightSample]("als")
        self.temperature = LatestValueBuffer[TemperatureSample]("temperature")
        self.hand_tracking = LatestValueBuffer[HandTrackingSample]("hand_tracking")
        self.connection = LatestValueBuffer[ConnectionSample]("connection")
        self.performance = LatestValueBuffer[PerformanceSample]("performance")
        self.logs = LatestValueBuffer[str]("logs")
        self.recording = RecordingState()
        self.toggles = StreamToggles()
        self._toggles_lock = threading.Lock()
        self._recording_lock = threading.Lock()

    def set_toggles(self, toggles: StreamToggles) -> None:
        with self._toggles_lock:
            self.toggles = toggles

    def get_toggles(self) -> StreamToggles:
        with self._toggles_lock:
            return StreamToggles(**vars(self.toggles))

    def update_recording(self, **kwargs: Any) -> RecordingState:
        with self._recording_lock:
            for key, value in kwargs.items():
                if hasattr(self.recording, key):
                    setattr(self.recording, key, value)
            return RecordingState(**vars(self.recording))

    def get_recording(self) -> RecordingState:
        with self._recording_lock:
            return RecordingState(**vars(self.recording))

    def buffer_overwrites(self) -> Dict[str, int]:
        return {
            "rgb": self.rgb_frame.snapshot().overwrite_count,
            "et_left": self.et_left_frame.snapshot().overwrite_count,
            "et_right": self.et_right_frame.snapshot().overwrite_count,
            "eye": self.eye_tracking.snapshot().overwrite_count,
            "hr": self.heart_rate.snapshot().overwrite_count,
            "hand": self.hand_tracking.snapshot().overwrite_count,
        }
