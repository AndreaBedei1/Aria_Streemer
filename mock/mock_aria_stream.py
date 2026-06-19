from __future__ import annotations

import logging
import threading
import time

from aria_recording_manager import AriaRecordingManager
from config import AppConfig
from mock import mock_data_generators as gen
from processing.fps_counter import FpsCounter
from processing.gaze_projection import looking_state, project_gaze_to_rgb
from processing.image_conversion import normalize_image_for_display
from processing.ppg_hr import PpgHeartRateEstimator
from processing.pulse_variability import estimate_pulse_variability
from stream_state import (
    AmbientLightSample,
    ConnectionSample,
    EyeTrackingSample,
    HandTrackingSample,
    HeartRateSample,
    PerformanceSample,
    PpgSample,
    PupilSample,
    PulseVariabilitySample,
    SharedStreamState,
    TemperatureSample,
    VideoFrame,
)


LOG = logging.getLogger(__name__)


class MockAriaStreamWorker:
    def __init__(
        self,
        config: AppConfig,
        state: SharedStreamState,
        recording_manager: AriaRecordingManager,
    ):
        self.config = config
        self.state = state
        self.recording_manager = recording_manager
        self._connected = False
        self._streaming = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ppg = PpgHeartRateEstimator(
            sample_rate_hz=config.ppg_sample_rate_hz, window_s=10.0
        )
        self._fps = {
            "rgb": FpsCounter(),
            "et": FpsCounter(),
            "eye": FpsCounter(),
            "ht": FpsCounter(),
            "ppg": FpsCounter(),
            "bpm": FpsCounter(window_s=10.0),
        }
        self._last_hr = 0.0
        self._last_pv = 0.0

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def streaming(self) -> bool:
        return self._streaming

    def connect(self) -> None:
        self._connected = True
        self.state.connection.set(
            ConnectionSample(
                timestamp_s=time.monotonic(),
                connected=True,
                streaming=False,
                recording=False,
                mode="mock",
                device_id="MOCK-ARIA-GEN2",
                sdk_version="mock",
                status_message="Mock glasses connected",
                profile_name=self.config.streaming_profile,
            )
        )
        self.state.logs.set("Mock mode active: generated RGB, gaze, PPG, pupils and hands")

    def disconnect(self) -> None:
        self.stop_streaming()
        self._connected = False
        self.state.connection.set(
            ConnectionSample(
                timestamp_s=time.monotonic(),
                connected=False,
                streaming=False,
                recording=self.state.get_recording().active,
                mode="mock",
                sdk_version="mock",
                status_message="Disconnected",
            )
        )

    def start_streaming(self) -> None:
        if not self._connected:
            self.connect()
        if self._streaming:
            return
        self._stop.clear()
        self._streaming = True
        self._thread = threading.Thread(target=self._loop, name="mock-aria", daemon=True)
        self._thread.start()
        self.state.logs.set("Mock streaming started")

    def stop_streaming(self) -> None:
        if not self._streaming:
            return
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._streaming = False
        self.state.logs.set("Mock streaming stopped")

    def reset_statistics(self) -> None:
        for counter in self._fps.values():
            counter.reset()
        self._ppg.clear()
        self.state.logs.set("Statistics reset")

    def note_toggles_changed(self) -> None:
        return

    def _loop(self) -> None:
        start = time.monotonic()
        next_rgb = next_et = next_eye = next_ht = next_ppg = next_aux = start
        frame_no = 0
        while not self._stop.is_set():
            now = time.monotonic()
            t = now - start
            toggles = self.state.get_toggles()

            if toggles.rgb and now >= next_rgb:
                frame_no += 1
                img = gen.rgb_frame(self.config.rgb_width, self.config.rgb_height, t)
                display, metadata = normalize_image_for_display(
                    img, source_name="mock RGB"
                )
                metadata["frame_number"] = frame_no
                self._fps["rgb"].tick(frame_no)
                self.state.rgb_frame.set(
                    VideoFrame(
                        image_rgb=display,
                        capture_timestamp_ns=int(now * 1e9),
                        camera_id=64,
                        label="mock RGB",
                        width=display.shape[1],
                        height=display.shape[0],
                        metadata=metadata,
                        valid=bool(metadata.get("valid", True)),
                        warning=str(metadata.get("warning", "")),
                    )
                )
                next_rgb = now + 1.0 / self.config.rgb_fps

            if toggles.et_cameras and now >= next_et:
                left = gen.et_frame(200, t, "left")
                right = gen.et_frame(200, t, "right")
                left_display, left_meta = normalize_image_for_display(
                    left, source_name="ET left"
                )
                right_display, right_meta = normalize_image_for_display(
                    right, source_name="ET right"
                )
                self._fps["et"].tick()
                self.state.et_left_frame.set(
                    VideoFrame(
                        left_display,
                        int(now * 1e9),
                        16,
                        "ET left",
                        200,
                        200,
                        metadata=left_meta,
                        valid=bool(left_meta.get("valid", True)),
                        warning=str(left_meta.get("warning", "")),
                    )
                )
                self.state.et_right_frame.set(
                    VideoFrame(
                        right_display,
                        int(now * 1e9),
                        32,
                        "ET right",
                        200,
                        200,
                        metadata=right_meta,
                        valid=bool(right_meta.get("valid", True)),
                        warning=str(right_meta.get("warning", "")),
                    )
                )
                next_et = now + 1.0 / max(1, self.config.et_fps)

            if (toggles.eye_tracking or toggles.blink_perclos or toggles.pupils) and now >= next_eye:
                yaw, pitch, valid = gen.gaze(t)
                rgb = self.state.rgb_frame.get()
                point = project_gaze_to_rgb(
                    yaw, pitch, rgb.width if rgb else 960, rgb.height if rgb else 540
                )
                eye_state = "Eyes open" if valid else "Blinking"
                self._fps["eye"].tick()
                self.state.eye_tracking.set(
                    EyeTrackingSample(
                        timestamp_s=now,
                        yaw_rad=yaw,
                        pitch_rad=pitch,
                        depth_m=1.2,
                        combined_gaze_valid=valid,
                        gaze_point_rgb=point,
                        eye_state=eye_state,
                        looking_state=looking_state(yaw, pitch) if valid else eye_state,
                        blink_rate_per_min=12.0,
                        perclos=0.05,
                    )
                )
                lux, _ = gen.ambient_lux(t)
                left_d, right_d = gen.pupil(t, lux)
                self.state.pupils.set(
                    PupilSample(
                        timestamp_s=now,
                        left_center=(96.0, 100.0),
                        right_center=(104.0, 101.0),
                        left_diameter_mm=left_d,
                        right_diameter_mm=right_d,
                        ambient_lux=lux,
                        note="mock",
                    )
                )
                next_eye = now + 0.1

            if toggles.hand_tracking and now >= next_ht:
                left = gen.hand_side(t, "left")
                right = gen.hand_side(t + 1.2, "right")
                self._fps["ht"].tick()
                self.state.hand_tracking.set(
                    HandTrackingSample(
                        timestamp_s=now,
                        left=left,
                        right=right,
                        message="Mock hand tracking active",
                    )
                )
                next_ht = now + 1.0 / max(1, self.config.ht_fps)

            if toggles.heart_rate and now >= next_ppg:
                value = gen.ppg_value(t)
                self._ppg.add_sample(now, value)
                self._fps["ppg"].tick()
                self.state.logs.set(self.state.logs.get() or "")
                next_ppg = now + 1.0 / self.config.ppg_sample_rate_hz
                if now - self._last_hr >= 1.0 / self.config.hr_update_hz:
                    self._last_hr = now
                    estimate = self._ppg.estimate()
                    self._fps["bpm"].tick()
                    self.state.heart_rate.set(
                        HeartRateSample(
                            timestamp_s=now,
                            bpm=estimate.bpm,
                            quality=estimate.quality.label,
                            quality_score=estimate.quality.score,
                            trend=estimate.trend,
                            source="mock PPG",
                            message=estimate.message,
                            ppg_plot=estimate.plot_points,
                        )
                    )
                    if now - self._last_pv >= 30.0:
                        self._last_pv = now
                        times, filtered = self._ppg.values_for_variability()
                        pv = estimate_pulse_variability(
                            times,
                            filtered,
                            self.config.ppg_sample_rate_hz,
                            estimate.quality.label,
                            min_window_s=8.0,
                        )
                        self.state.pulse_variability.set(
                            PulseVariabilitySample(now, pv.rmssd_ms, pv.status, pv.peak_count)
                        )

            if now >= next_aux:
                lux, light_state = gen.ambient_lux(t)
                self.state.als.set(AmbientLightSample(now, lux, light_state, "mock"))
                self.state.temperature.set(
                    TemperatureSample(
                        timestamp_s=now,
                        temperature_c=36.5 + 1.5 * (0.5 + 0.5),
                        sensor_name="mock device",
                        warning=False,
                    )
                )
                self.state.performance.set(
                    PerformanceSample(
                        timestamp_s=now,
                        fps={k: v.value for k, v in self._fps.items()},
                        dropped_frames={k: v.dropped_frames for k, v in self._fps.items()},
                        overwrite_counts=self.state.buffer_overwrites(),
                        connection_state="Streaming",
                        recording_state="ON" if self.state.get_recording().active else "OFF",
                    )
                )
                self.state.connection.set(
                    ConnectionSample(
                        timestamp_s=now,
                        connected=True,
                        streaming=True,
                        recording=self.state.get_recording().active,
                        mode="mock",
                        device_id="MOCK-ARIA-GEN2",
                        sdk_version="mock",
                        status_message="Mock streaming",
                        profile_name=self.config.streaming_profile,
                    )
                )
                next_aux = now + 1.0

            time.sleep(0.001)
