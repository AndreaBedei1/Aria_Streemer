from __future__ import annotations

import importlib.metadata
import json
import logging
import math
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Iterable, Optional, Tuple

import numpy as np

from aria_recording_manager import AriaRecordingManager
from config import AppConfig
from processing.downsampling import RateLimiter, resize_keep_aspect
from processing.fps_counter import FpsCounter
from processing.gaze_projection import looking_state, project_gaze_to_rgb
from processing.image_conversion import normalize_image_for_display
from processing.ppg_hr import PpgHeartRateEstimator
from processing.pulse_variability import estimate_pulse_variability
from stream_state import (
    AmbientLightSample,
    ConnectionSample,
    EyeTrackingSample,
    HandSideSample,
    HandTrackingSample,
    HeartRateSample,
    PerformanceSample,
    Point3D,
    PulseVariabilitySample,
    SharedStreamState,
    TemperatureSample,
    VideoFrame,
)


LOG = logging.getLogger(__name__)


class BlinkPerclosTracker:
    def __init__(self, perclos_window_s: float = 30.0, blink_window_s: float = 60.0):
        self.perclos_window_s = perclos_window_s
        self.blink_window_s = blink_window_s
        self.samples: Deque[Tuple[float, bool]] = deque()
        self.blinks: Deque[float] = deque()
        self._closed_started_at: Optional[float] = None
        self._last_valid: Optional[bool] = None

    def update(self, timestamp_s: float, valid: Optional[bool]) -> Tuple[str, float, float]:
        if valid is None:
            return "Waiting for data...", 0.0, 0.0
        closed = not valid
        self.samples.append((timestamp_s, closed))
        while self.samples and timestamp_s - self.samples[0][0] > self.perclos_window_s:
            self.samples.popleft()
        while self.blinks and timestamp_s - self.blinks[0] > self.blink_window_s:
            self.blinks.popleft()

        if closed and self._last_valid is not False:
            self._closed_started_at = timestamp_s
        if not closed and self._last_valid is False and self._closed_started_at is not None:
            duration = timestamp_s - self._closed_started_at
            if 0.05 <= duration <= 0.45:
                self.blinks.append(timestamp_s)
            self._closed_started_at = None
        self._last_valid = valid

        perclos = sum(1 for _, is_closed in self.samples if is_closed) / max(
            1, len(self.samples)
        )
        blink_rate = len(self.blinks) * (60.0 / self.blink_window_s)

        if closed:
            if self._closed_started_at is not None and timestamp_s - self._closed_started_at > 0.65:
                state = "Eyes closed"
            else:
                state = "Blinking"
        else:
            state = "Eyes open"
        return state, blink_rate, perclos


class AriaStreamWorker:
    def __init__(
        self,
        config: AppConfig,
        state: SharedStreamState,
        recording_manager: AriaRecordingManager,
    ):
        self.config = config
        self.state = state
        self.recording_manager = recording_manager
        self._sdk_gen2: Any = None
        self._receiver_module: Any = None
        self._device_client: Any = None
        self._device: Any = None
        self._stream_receiver: Any = None
        self._connected = False
        self._streaming = False
        self._stop_monitor = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._sdk_version = "unknown"
        self._blink = BlinkPerclosTracker()
        self._ppg = PpgHeartRateEstimator(
            sample_rate_hz=config.ppg_sample_rate_hz, window_s=10.0
        )
        self._last_hr_emit = 0.0
        self._last_pv_emit = 0.0
        self._last_rgb_success = 0.0
        self._last_rgb_error_log = 0.0
        self._using_slam_fallback = False
        self._debug_dump_counts = {"RGB": 0, "SLAM": 0, "ET": 0}
        self._rgb_limiter = RateLimiter(config.rgb_fps)
        self._et_limiter = RateLimiter(config.et_fps)
        self._ht_limiter = RateLimiter(config.ht_fps)
        self._fps = {
            "rgb": FpsCounter(),
            "et": FpsCounter(),
            "eye": FpsCounter(),
            "ht": FpsCounter(),
            "ppg": FpsCounter(),
            "bpm": FpsCounter(window_s=10.0),
        }
        self._device_ip = config.device_ip

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def streaming(self) -> bool:
        return self._streaming

    def connect(self) -> None:
        with self._lock:
            if self._connected:
                return
            self._import_sdk()
            assert self._sdk_gen2 is not None
            self._device_client = self._sdk_gen2.DeviceClient()
            client_config = self._sdk_gen2.DeviceClientConfig()
            self._device_client.set_client_config(client_config)

            target_ip = self._device_ip or os.getenv("ARIA_DEVICE_IP", "")
            if self.config.connection_mode == "wifi" and target_ip:
                target = self._sdk_gen2.DeviceTarget(ip=target_ip)
                self._device = self._device_client.connect(target)
            elif target_ip:
                try:
                    self._device = self._device_client.connect(
                        self._sdk_gen2.DeviceTarget(ip=target_ip)
                    )
                except Exception:
                    LOG.info("IP connect failed; trying SDK default discovery")
                    self._device = self._device_client.connect()
            else:
                self._device = self._device_client.connect()

            device_id = self._safe_call(self._device.connection_id, "")
            serial = self._safe_call(self._device.serial, device_id)
            status = self._safe_call(self._device.status, None)
            if status is not None:
                self._device_ip = str(getattr(status, "wifi_ip_address", "") or target_ip)
            self.recording_manager.set_device(self._device, self._sdk_gen2)
            self._connected = True
            self._log_device_context(status)
            self._update_connection("Connected", device_id=serial)
            self._start_monitor()

    def disconnect(self) -> None:
        with self._lock:
            self.stop_streaming()
            if self._device_client is not None and self._device is not None:
                try:
                    self._device_client.disconnect(self._device)
                except Exception:
                    LOG.exception("Failed to disconnect device")
            self._device = None
            self._device_client = None
            self._connected = False
            self.recording_manager.clear_device()
            self._stop_monitor.set()
            self._update_connection("Disconnected")

    def start_streaming(self) -> None:
        with self._lock:
            if self._streaming:
                return
            if not self._connected:
                self.connect()
            assert self._sdk_gen2 is not None
            assert self._receiver_module is not None
            assert self._device is not None

            toggles = self.state.get_toggles()
            streaming_config = self._sdk_gen2.HttpStreamingConfig()
            streaming_config.profile_name = self.config.streaming_profile
            cert_name = self._local_streaming_cert_name()
            if cert_name and hasattr(streaming_config, "streaming_cert_name"):
                streaming_config.streaming_cert_name = cert_name
            try:
                streaming_config.advanced_config.endpoint.verify_server_certificates = False
            except Exception:
                pass
            if hasattr(streaming_config, "streaming_interface"):
                if self.config.connection_mode == "wifi":
                    streaming_config.streaming_interface = (
                        self._sdk_gen2.StreamingInterface.WIFI_STA
                    )
                    streaming_config.batch_period_ms = 200
                else:
                    streaming_config.streaming_interface = (
                        self._sdk_gen2.StreamingInterface.USB_NCM
                    )
            self._device.set_streaming_config(streaming_config)

            image_decode_needed = toggles.rgb or toggles.et_cameras
            self._stream_receiver = self._receiver_module.StreamReceiver(
                enable_image_decoding=image_decode_needed,
                enable_raw_stream=False,
            )
            self._configure_receiver(self._stream_receiver, toggles)
            try:
                self._stream_receiver.start_server()
                self._device.start_streaming()
            except Exception:
                try:
                    self._stream_receiver.stop_server()
                except Exception:
                    pass
                self._stream_receiver = None
                raise
            self._streaming = True
            self._update_connection("Streaming")
            LOG.info("Started streaming profile=%s", self.config.streaming_profile)

    def stop_streaming(self) -> None:
        with self._lock:
            if not self._streaming and self._stream_receiver is None:
                return
            if self._device is not None and self._streaming:
                try:
                    self._device.stop_streaming()
                except Exception:
                    LOG.exception("Failed to stop device streaming")
            if self._stream_receiver is not None:
                try:
                    self._stream_receiver.stop_server()
                except Exception:
                    LOG.exception("Failed to stop stream receiver")
            self._stream_receiver = None
            self._streaming = False
            self._update_connection("Connected")

    def reset_statistics(self) -> None:
        for counter in self._fps.values():
            counter.reset()
        self._ppg.clear()
        self._blink = BlinkPerclosTracker()
        self.state.logs.set("Statistics reset")

    def note_toggles_changed(self) -> None:
        if self._streaming:
            self.state.logs.set(
                "Stream selection changed. Restart streaming to apply SDK decoder subscriptions."
            )

    def _import_sdk(self) -> None:
        if self._sdk_gen2 is not None:
            return
        import aria.sdk_gen2 as sdk_gen2
        import aria.stream_receiver as receiver

        self._sdk_gen2 = sdk_gen2
        self._receiver_module = receiver
        try:
            self._sdk_version = importlib.metadata.version("projectaria-client-sdk")
        except Exception:
            self._sdk_version = "unknown"
        LOG.info("Project Aria Client SDK version: %s", self._sdk_version)

    def _configure_receiver(self, stream_receiver: Any, toggles: Any) -> None:
        config = self._sdk_gen2.HttpServerConfig()
        config.address = "0.0.0.0"
        config.port = self.config.http_server_port
        if hasattr(config, "use_ssl") and not self._local_streaming_cert_name():
            config.use_ssl = False
        stream_receiver.set_server_config(config)

        for setter in (
            "set_rgb_queue_size",
            "set_slam_queue_size",
            "set_et_queue_size",
            "set_eye_gaze_queue_size",
            "set_hand_pose_queue_size",
            "set_vio_queue_size",
        ):
            if hasattr(stream_receiver, setter):
                getattr(stream_receiver, setter)(1)

        if toggles.rgb:
            stream_receiver.register_rgb_callback(self._rgb_callback)
            stream_receiver.register_slam_callback(self._slam_callback)
        if toggles.et_cameras:
            stream_receiver.register_et_callback(self._et_callback)
        if toggles.eye_tracking or toggles.blink_perclos:
            stream_receiver.register_eye_gaze_callback(self._eye_gaze_callback)
        if toggles.hand_tracking:
            stream_receiver.register_hand_pose_callback(self._hand_pose_callback)
        if toggles.heart_rate or toggles.ppg_quality or toggles.pulse_variability:
            stream_receiver.register_ppg_callback(self._ppg_callback)
        if toggles.temperature:
            stream_receiver.register_barometer_callback(self._barometer_callback)

    def _rgb_callback(self, image_data: Any, image_record: Any, *args: Any) -> None:
        if not self.state.get_toggles().rgb or not self._rgb_limiter.allow():
            return
        try:
            arr, metadata = normalize_image_for_display(
                image_data, image_record, source_name="RGB"
            )
            self._maybe_dump_image("RGB", arr, metadata)
            if not metadata.get("valid", False):
                self._reject_image("RGB", metadata)
                return
            arr = resize_keep_aspect(arr, self.config.rgb_width, self.config.rgb_height)
            self._store_video_frame("RGB", arr, metadata)
            self._last_rgb_success = time.monotonic()
            self._using_slam_fallback = False
        except Exception as exc:
            self.state.logs.set(f"RGB frame rejected: {exc}")

    def _slam_callback(self, image_data: Any, image_record: Any, *args: Any) -> None:
        if not self.state.get_toggles().rgb:
            return
        if time.monotonic() - self._last_rgb_success < 1.5:
            return
        try:
            arr, metadata = normalize_image_for_display(
                image_data, image_record, source_name="SLAM"
            )
            self._maybe_dump_image("SLAM", arr, metadata)
            if not metadata.get("valid", False):
                self._reject_image("SLAM", metadata)
                return
            arr = self._force_grayscale_rgb(arr)
            arr = resize_keep_aspect(arr, self.config.rgb_width, self.config.rgb_height)
            metadata["conversion_path"] = f"{metadata.get('conversion_path', 'unknown')}+grayscale"
            self._store_video_frame("SLAM grayscale preview", arr, metadata)
            if not self._using_slam_fallback:
                self._using_slam_fallback = True
                self.state.logs.set("SLAM frame accepted")
        except Exception as exc:
            self.state.logs.set(f"SLAM frame rejected: {exc}")

    def _store_video_frame(self, label: str, arr: np.ndarray, metadata: dict) -> None:
        height, width = arr.shape[:2]
        self._fps["rgb"].tick(metadata.get("frame_number"))
        self.state.rgb_frame.set(
            VideoFrame(
                image_rgb=arr.copy(),
                capture_timestamp_ns=int(metadata.get("capture_timestamp_ns") or 0),
                camera_id=int(metadata.get("camera_id") or 0),
                label=label,
                width=width,
                height=height,
                metadata=metadata,
                valid=True,
                warning=str(metadata.get("warning", "")),
            )
        )

    def _reject_image(self, source: str, metadata: dict) -> None:
        warning = metadata.get("warning") or metadata.get("error") or "invalid image"
        self.state.logs.set(f"{source} frame rejected: {warning}")

    def _maybe_dump_image(self, source: str, arr: np.ndarray, metadata: dict) -> None:
        if not self.config.debug_image_dump:
            return
        source_key = source.upper()
        count = self._debug_dump_counts.get(source_key, 0)
        if count >= 10:
            return
        self._debug_dump_counts[source_key] = count + 1
        out_dir = Path(self.config.debug_image_dump).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        prefix = out_dir / f"{source_key.lower()}_{count:03d}"
        try:
            import cv2

            cv2.imwrite(str(prefix.with_suffix(".png")), arr[:, :, ::-1])
        except Exception:
            try:
                from PIL import Image

                Image.fromarray(arr).save(prefix.with_suffix(".png"))
            except Exception as exc:
                LOG.warning("Failed to write debug image %s: %s", prefix, exc)
        try:
            with prefix.with_suffix(".json").open("w", encoding="utf-8") as handle:
                json.dump(metadata, handle, indent=2, default=str)
        except Exception as exc:
            LOG.warning("Failed to write debug metadata %s: %s", prefix, exc)

    @staticmethod
    def _force_grayscale_rgb(arr: np.ndarray) -> np.ndarray:
        rgb = np.asarray(arr)
        if rgb.ndim == 2:
            gray = rgb
        else:
            gray = rgb[:, :, :3].astype(np.float32).mean(axis=2)
        finite = np.isfinite(gray)
        if not np.any(finite):
            gray_u8 = np.zeros(gray.shape, dtype=np.uint8)
        else:
            lo = float(np.percentile(gray[finite], 1))
            hi = float(np.percentile(gray[finite], 99))
            if hi <= lo:
                hi = lo + 1.0
            gray_u8 = np.clip((gray - lo) * (255.0 / (hi - lo)), 0, 255).astype(
                np.uint8
            )
        return np.ascontiguousarray(np.repeat(gray_u8[:, :, None], 3, axis=2))

    def _et_callback(self, image_data: Any, image_record: Any, *args: Any) -> None:
        if not self.state.get_toggles().et_cameras or not self._et_limiter.allow():
            return
        try:
            arr, metadata = normalize_image_for_display(
                image_data, image_record, source_name="ET"
            )
            self._maybe_dump_image("ET", arr, metadata)
            if not metadata.get("valid", False):
                self._reject_image("ET", metadata)
                return
            arr = resize_keep_aspect(arr, 220, 220)
            camera_id = int(metadata.get("camera_id") or 0)
            label = "ET left" if camera_id == 16 else "ET right"
            frame = VideoFrame(
                image_rgb=arr.copy(),
                capture_timestamp_ns=int(metadata.get("capture_timestamp_ns") or 0),
                camera_id=camera_id,
                label=label,
                width=arr.shape[1],
                height=arr.shape[0],
                metadata=metadata,
                valid=True,
                warning=str(metadata.get("warning", "")),
            )
            self._fps["et"].tick(metadata.get("frame_number"))
            if camera_id == 16:
                self.state.et_left_frame.set(frame)
            elif camera_id == 32:
                self.state.et_right_frame.set(frame)
            else:
                self.state.et_left_frame.set(frame)
        except Exception as exc:
            LOG.warning("ET camera display failed: %s", exc)
            self.state.logs.set(f"ET cameras not available: {exc}")

    def _eye_gaze_callback(self, eyegaze_data: Any, *args: Any) -> None:
        self._fps["eye"].tick()
        try:
            ts = self._timestamp_from_tracking(eyegaze_data)
            yaw = self._finite_or_none(getattr(eyegaze_data, "yaw", None))
            pitch = self._finite_or_none(getattr(eyegaze_data, "pitch", None))
            depth = self._finite_or_none(getattr(eyegaze_data, "depth", None))
            valid = getattr(eyegaze_data, "combined_gaze_valid", None)
            valid = bool(valid) if valid is not None else None
            eye_state, blink_rate, perclos = self._blink.update(ts, valid)
            rgb = self.state.rgb_frame.get()
            gaze_pt = None
            if rgb is not None:
                gaze_pt = project_gaze_to_rgb(yaw, pitch, rgb.width, rgb.height)
            sample = EyeTrackingSample(
                timestamp_s=ts,
                yaw_rad=yaw,
                pitch_rad=pitch,
                depth_m=depth,
                combined_gaze_valid=valid,
                gaze_point_rgb=gaze_pt,
                eye_state=eye_state,
                looking_state=looking_state(yaw, pitch) if valid is not False else eye_state,
                blink_rate_per_min=blink_rate,
                perclos=perclos,
            )
            self.state.eye_tracking.set(sample)
            self.state.pupils.set(
                self.state.pupils.get()
                or self._missing_pupil_sample(ts, "Pupil diameter not exposed by live EyeGaze SDK callback")
            )
        except Exception as exc:
            LOG.warning("Eye tracking callback failed: %s", exc)
            self.state.logs.set(f"Eye tracking not available: {exc}")

    def _hand_pose_callback(self, handtracking_data: Any, *args: Any) -> None:
        if not self._ht_limiter.allow():
            return
        self._fps["ht"].tick()
        try:
            ts = self._timestamp_from_tracking(handtracking_data)
            left = self._hand_side(getattr(handtracking_data, "left_hand", None))
            right = self._hand_side(getattr(handtracking_data, "right_hand", None))
            message = "Hand tracking active"
            if not left.visible and not right.visible:
                message = "Hands not visible"
            self.state.hand_tracking.set(
                HandTrackingSample(timestamp_s=ts, left=left, right=right, message=message)
            )
        except Exception as exc:
            LOG.warning("Hand tracking callback failed: %s", exc)
            self.state.logs.set(f"Hand tracking not available: {exc}")

    def _ppg_callback(self, ppg_data: Any, *args: Any) -> None:
        samples = ppg_data if isinstance(ppg_data, Iterable) and not hasattr(ppg_data, "value") else [ppg_data]
        for sample in samples:
            try:
                value = float(getattr(sample, "value"))
                ts_ns = int(getattr(sample, "capture_timestamp_ns", 0))
                ts = ts_ns / 1e9 if ts_ns > 0 else time.monotonic()
                self._ppg.add_sample(ts, value)
                self._fps["ppg"].tick()
            except Exception:
                continue

        now = time.monotonic()
        if now - self._last_hr_emit < 1.0 / self.config.hr_update_hz:
            return
        self._last_hr_emit = now
        estimate = self._ppg.estimate()
        self._fps["bpm"].tick()
        self.state.heart_rate.set(
            HeartRateSample(
                timestamp_s=now,
                bpm=estimate.bpm,
                quality=estimate.quality.label,
                quality_score=estimate.quality.score,
                trend=estimate.trend,
                source="PPG raw",
                message=estimate.message,
                ppg_plot=estimate.plot_points,
            )
        )
        if now - self._last_pv_emit >= 30.0:
            self._last_pv_emit = now
            times, filtered = self._ppg.values_for_variability()
            pv = estimate_pulse_variability(
                times,
                filtered,
                self.config.ppg_sample_rate_hz,
                estimate.quality.label,
                min_window_s=30.0,
            )
            self.state.pulse_variability.set(
                PulseVariabilitySample(
                    timestamp_s=now,
                    rmssd_ms=pv.rmssd_ms,
                    status=pv.status,
                    peak_count=pv.peak_count,
                )
            )

    def _barometer_callback(self, baro_data: Any, *args: Any) -> None:
        try:
            temp = self._finite_or_none(getattr(baro_data, "temperature", None))
            ts_ns = int(getattr(baro_data, "capture_timestamp_ns", 0))
            ts = ts_ns / 1e9 if ts_ns > 0 else time.monotonic()
            self.state.temperature.set(self._temperature_sample(ts, temp, "barometer"))
        except Exception as exc:
            LOG.warning("Temperature/barometer callback failed: %s", exc)

    def _start_monitor(self) -> None:
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._stop_monitor.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, name="aria-monitor", daemon=True
        )
        self._monitor_thread.start()

    def _monitor_loop(self) -> None:
        try:
            import psutil
        except Exception:
            psutil = None

        while not self._stop_monitor.wait(1.0):
            try:
                status = self._safe_call(self._device.status, None) if self._device else None
                device_id = self._safe_call(self._device.connection_id, "") if self._device else ""
                is_recording = bool(self._safe_call(self._device.is_recording, False)) if self._device else False
                if is_recording and not self.state.get_recording().active:
                    self.state.update_recording(
                        active=True,
                        session_name="device_recording",
                        started_at=time.monotonic(),
                        device_side=True,
                    )
                if not is_recording and self.state.get_recording().active:
                    rec = self.state.get_recording()
                    if not rec.starting and not rec.stopping:
                        self.state.update_recording(active=False)
                if status is not None:
                    temp = self._finite_or_none(getattr(status, "skin_temp_celsius", None))
                    if temp is not None:
                        self.state.temperature.set(
                            self._temperature_sample(time.monotonic(), temp, "device skin")
                        )
                    self._device_ip = str(getattr(status, "wifi_ip_address", "") or self._device_ip)
                cpu = psutil.cpu_percent(interval=None) if psutil is not None else None
                ram = psutil.virtual_memory().percent if psutil is not None else None
                perf = PerformanceSample(
                    timestamp_s=time.monotonic(),
                    fps={k: v.value for k, v in self._fps.items()},
                    dropped_frames={k: v.dropped_frames for k, v in self._fps.items()},
                    overwrite_counts=self.state.buffer_overwrites(),
                    cpu_percent=cpu,
                    ram_percent=ram,
                    connection_state="Streaming" if self._streaming else "Connected",
                    recording_state="ON" if is_recording else "OFF",
                )
                self.state.performance.set(perf)
                self._update_connection(
                    "Streaming" if self._streaming else "Connected",
                    device_id=device_id,
                    recording=is_recording,
                )
                if self.state.als.get() is None:
                    self.state.als.set(
                        AmbientLightSample(
                            timestamp_s=time.monotonic(),
                            lux=None,
                            state="NOT AVAILABLE",
                            message="ALS callback is not exposed by this SDK receiver build",
                        )
                    )
            except Exception:
                LOG.exception("Monitor loop failed")

    def _log_device_context(self, status: Any) -> None:
        device_id = self._safe_call(self._device.connection_id, "") if self._device else ""
        LOG.info("Connected device: %s", device_id)
        LOG.info("SDK version: %s", self._sdk_version)
        LOG.info("Connection mode: %s", self.config.connection_mode)
        LOG.info("Streaming profile: %s", self.config.streaming_profile)
        LOG.info("Recording profile: %s", self.config.recording_profile)
        if status is not None:
            LOG.info("Device status fields: %s", self._public_attrs(status))
        profiles = self._safe_call(self._device.device_profiles, {}) if self._device else {}
        LOG.info("Device profiles available: %s", profiles)
        self.state.logs.set(
            f"SDK {self._sdk_version} | device {device_id} | streaming profile {self.config.streaming_profile}"
        )

    @staticmethod
    def _local_streaming_cert_name() -> str:
        cert_name_path = os.path.expanduser(
            "~/.aria/streaming-certs/persistent/publisher-cert-name"
        )
        try:
            with open(cert_name_path, "r", encoding="utf-8") as handle:
                return handle.read().strip()
        except Exception:
            return ""

    def _update_connection(
        self, message: str, device_id: str = "", recording: Optional[bool] = None
    ) -> None:
        rec = self.state.get_recording()
        self.state.connection.set(
            ConnectionSample(
                timestamp_s=time.monotonic(),
                connected=self._connected,
                streaming=self._streaming,
                recording=rec.active if recording is None else recording,
                mode=self.config.connection_mode,
                device_id=device_id,
                device_ip=self._device_ip,
                sdk_version=self._sdk_version,
                status_message=message,
                profile_name=self.config.streaming_profile,
            )
        )

    def _hand_side(self, hand: Any) -> HandSideSample:
        if hand is None:
            return HandSideSample(visible=False)
        landmarks = []
        raw_landmarks = getattr(hand, "landmark_positions_device", None)
        if raw_landmarks is not None:
            landmarks = [self._vec3(point) for point in raw_landmarks]
        return HandSideSample(
            visible=True,
            confidence=self._finite_or_none(getattr(hand, "confidence", None)),
            landmarks_device=[p for p in landmarks if p is not None],
            wrist_device=self._vec3(self._safe_call(hand.get_wrist_position_device, None)),
            palm_device=self._vec3(self._safe_call(hand.get_palm_position_device, None)),
        )

    def _missing_pupil_sample(self, timestamp_s: float, note: str) -> Any:
        from stream_state import PupilSample

        return PupilSample(timestamp_s=timestamp_s, note=note)

    def _temperature_sample(
        self, timestamp_s: float, temp_c: Optional[float], sensor_name: str
    ) -> TemperatureSample:
        warning = temp_c is not None and temp_c >= self.config.temperature_warning_c
        message = "High device temperature" if warning else ""
        if temp_c is None:
            message = "Temperature not available"
        return TemperatureSample(
            timestamp_s=timestamp_s,
            temperature_c=temp_c,
            sensor_name=sensor_name,
            warning=warning,
            message=message,
        )

    def _timestamp_from_tracking(self, data: Any) -> float:
        ts = getattr(data, "tracking_timestamp", None)
        if ts is not None and hasattr(ts, "total_seconds"):
            return float(ts.total_seconds())
        capture_ns = getattr(data, "capture_timestamp_ns", 0)
        if capture_ns:
            return float(capture_ns) / 1e9
        return time.monotonic()

    @staticmethod
    def _finite_or_none(value: Any) -> Optional[float]:
        try:
            val = float(value)
        except Exception:
            return None
        return val if math.isfinite(val) else None

    @staticmethod
    def _vec3(value: Any) -> Optional[Point3D]:
        if value is None:
            return None
        try:
            arr = np.asarray(value, dtype=float).reshape(-1)
            if arr.size < 3:
                return None
            return (float(arr[0]), float(arr[1]), float(arr[2]))
        except Exception:
            return None

    @staticmethod
    def _safe_call(func: Any, default: Any) -> Any:
        try:
            return func()
        except Exception:
            return default

    @staticmethod
    def _public_attrs(obj: Any) -> dict[str, Any]:
        out = {}
        for name in dir(obj):
            if name.startswith("_"):
                continue
            try:
                value = getattr(obj, name)
            except Exception:
                continue
            if not callable(value):
                out[name] = value
        return out
