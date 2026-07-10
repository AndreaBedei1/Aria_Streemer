from __future__ import annotations

import importlib.metadata
import json
import logging
import math
import os
import socket
import threading
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, Deque, Iterable, Optional, Tuple

import numpy as np

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

if TYPE_CHECKING:
    from aria_recording_manager import AriaRecordingManager


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
        recording_manager: Optional[AriaRecordingManager] = None,
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
        self._preferred_slam_camera_id = 1
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
        self._device_serial = ""
        # Wi-Fi diagnostics / control-channel health, owned by the monitor loop.
        self._control_alive = True
        self._control_failures = 0
        self._last_reconnect_attempt = 0.0
        self._publishing: Optional[bool] = None
        self._publisher_ip = ""
        self._endpoint_url = ""
        self._battery_percent: Optional[int] = None
        self._charging: Optional[bool] = None
        self._wifi_ssid = ""
        self._active_interface = ""

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

            self._device = self._connect_control_channel()

            device_id = self._safe_call(self._device.connection_id, "")
            serial = self._safe_call(self._device.serial, device_id)
            self._device_serial = str(serial or "")
            status = self._safe_call(self._device.status, None)
            if status is not None:
                self._device_ip = str(
                    getattr(status, "wifi_ip_address", "") or self._device_ip
                )
                self._absorb_device_status(status)
            if self.recording_manager is not None:
                self.recording_manager.set_device(self._device, self._sdk_gen2)
            self._connected = True
            self._control_alive = True
            self._control_failures = 0
            self._log_device_context(status)
            self._update_connection("Connected", device_id=serial)
            self._start_monitor()

    def _connect_control_channel(self) -> Any:
        """Open the DeviceClient control channel.

        Wi-Fi mode follows the official Aria Gen 2 flow: the control channel
        may come up over USB (recommended: plug the cable, start streaming on
        WIFI_STA, then unplug) or directly over the network when the glasses
        IP is known (ARIA_DEVICE_IP / --device-ip).
        """
        target_ip = self._device_ip or os.getenv("ARIA_DEVICE_IP", "")
        attempts: list[str] = []

        if target_ip:
            try:
                LOG.info("Connecting control channel via IP %s", target_ip)
                device = self._device_client.connect(
                    self._sdk_gen2.DeviceTarget(ip=target_ip)
                )
                self._device_ip = target_ip
                return device
            except Exception as exc:
                attempts.append(f"ip {target_ip}: {exc}")
                LOG.warning(
                    "IP connect to %s failed (%s); trying SDK default discovery (USB)",
                    target_ip,
                    exc,
                )

        try:
            LOG.info("Connecting control channel via SDK default discovery (USB)")
            device = self._device_client.connect()
            if self.config.connection_mode == "wifi":
                LOG.info(
                    "Wi-Fi mode with USB control channel: streaming will use "
                    "WIFI_STA; the USB cable can be unplugged once streaming "
                    "has started."
                )
            return device
        except Exception as exc:
            attempts.append(f"default discovery: {exc}")

        detail = "; ".join(attempts)
        if self.config.connection_mode == "wifi":
            raise RuntimeError(
                "Could not reach the glasses. Tried: "
                f"{detail}. Plug the USB cable (official Wi-Fi flow) or set "
                "--device-ip/ARIA_DEVICE_IP to the glasses Wi-Fi IP "
                "(aria_gen2 device status)."
            )
        raise RuntimeError(
            f"Could not reach the glasses over USB. Tried: {detail}. "
            "Check the cable and run aria_gen2 device list."
        )

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
            self._control_alive = True
            self._control_failures = 0
            self._publishing = None
            self._publisher_ip = ""
            self._battery_percent = None
            self._charging = None
            if self.recording_manager is not None:
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

            streaming_config = self.build_streaming_config(self._device)
            self._device.set_streaming_config(streaming_config)

            toggles = self.state.get_toggles()
            image_decode_needed = toggles.rgb or toggles.et_cameras
            self._stream_receiver = self._receiver_module.StreamReceiver(
                enable_image_decoding=image_decode_needed,
                enable_raw_stream=False,
            )
            self._configure_receiver(self._stream_receiver, toggles)
            try:
                self._stream_receiver.start_server()
                LOG.info(
                    "Stream receiver listening on 0.0.0.0:%s (ssl=%s)",
                    self.config.http_server_port,
                    bool(self._local_streaming_cert_name()),
                )
                already = bool(self._safe_call(self._device.is_streaming, False))
                if already:
                    LOG.info(
                        "Device is already streaming; attaching the receiver "
                        "to the existing session instead of restarting it"
                    )
                    self.state.logs.set("Attached to the stream already running on the device")
                else:
                    self._device.start_streaming()
            except Exception:
                try:
                    self._stream_receiver.stop_server()
                except Exception:
                    pass
                self._stream_receiver = None
                raise
            self._streaming = True
            self._publishing = None
            self._publisher_ip = ""
            self._log_streaming_info()
            self._update_connection("Streaming")
            LOG.info("Started streaming profile=%s", self.config.streaming_profile)
            if self.config.connection_mode == "wifi":
                self.state.logs.set(
                    "Wi-Fi streaming started. The USB cable can be unplugged; "
                    "plug it back (or use the glasses IP) to stop the stream."
                )

    def build_streaming_config(self, device: Any) -> Any:
        """Build the HttpStreamingConfig for the current mode.

        USB keeps the historical behaviour. Wi-Fi mirrors the official flow
        (aria_gen2 streaming start --interface wifi_sta --batch-period-ms 200)
        plus keep_streaming_on_disconnection so the stream survives the USB
        unplug and transient Wi-Fi drops.
        """
        streaming_config = self._sdk_gen2.HttpStreamingConfig()
        streaming_config.profile_name = self.config.streaming_profile
        cert_name = self._local_streaming_cert_name()
        if cert_name and hasattr(streaming_config, "streaming_cert_name"):
            streaming_config.streaming_cert_name = cert_name
        try:
            streaming_config.advanced_config.endpoint.verify_server_certificates = False
        except Exception:
            pass

        batch_ms = self.config.effective_stream_batch_ms
        if hasattr(streaming_config, "streaming_interface"):
            if self.config.connection_mode == "wifi":
                streaming_config.streaming_interface = (
                    self._sdk_gen2.StreamingInterface.WIFI_STA
                )
            else:
                streaming_config.streaming_interface = (
                    self._sdk_gen2.StreamingInterface.USB_NCM
                )
            if hasattr(streaming_config, "batch_period_ms"):
                streaming_config.batch_period_ms = batch_ms

        if self.config.connection_mode == "wifi":
            self._prepare_wifi_streaming(device, streaming_config, cert_name)
        else:
            self._active_interface = "USB_NCM"
            self._endpoint_url = ""

        LOG.info(
            "Streaming config: interface=%s profile=%s batch_ms=%s cert=%s "
            "keep_on_disconnection=%s endpoint=%s",
            self._active_interface or self.config.connection_mode,
            self.config.streaming_profile,
            batch_ms,
            cert_name or "none (ssl off)",
            getattr(streaming_config, "keep_streaming_on_disconnection", "n/a"),
            self._endpoint_url or "SDK default (mDNS oatmeal_server.local)",
        )
        return streaming_config

    def _prepare_wifi_streaming(
        self, device: Any, streaming_config: Any, cert_name: str
    ) -> None:
        self._active_interface = "WIFI_STA"
        status = self._safe_call(device.status, None)
        wifi_connected = bool(getattr(status, "wifi_connected", False)) if status else False
        wifi_ip = str(getattr(status, "wifi_ip_address", "") or "") if status else ""
        ssid = str(getattr(status, "wifi_ssid", "") or "") if status else ""
        if status is not None and not wifi_connected:
            raise RuntimeError(
                "The glasses are not connected to a Wi-Fi network, so WIFI_STA "
                "streaming cannot start. Connect them first: aria_gen2 device "
                "wifi connect --ssid <SSID> --password <password>"
            )
        if wifi_ip:
            self._device_ip = wifi_ip
        if ssid:
            self._wifi_ssid = ssid
        LOG.info(
            "Glasses Wi-Fi status: connected=%s ssid=%s ip=%s",
            wifi_connected,
            ssid or "?",
            wifi_ip or "?",
        )

        # The device publishes to the receiver URL. The SDK default is
        # https://oatmeal_server.local:6768 resolved via mDNS, which breaks on
        # networks that block mDNS and can resolve to the USB-NCM address that
        # dies when the cable is unplugged. Prefer an explicit URL on the
        # host interface that routes towards the glasses Wi-Fi IP.
        endpoint = self.config.wifi_endpoint_url
        if not endpoint and wifi_ip:
            host_ip = self._host_ip_toward(wifi_ip)
            if host_ip:
                scheme = "https" if cert_name else "http"
                endpoint = f"{scheme}://{host_ip}:{self.config.http_server_port}"
        if endpoint:
            try:
                streaming_config.advanced_config.endpoint.url = endpoint
                self._endpoint_url = endpoint
            except Exception as exc:
                LOG.warning("Could not set explicit streaming endpoint: %s", exc)
                self._endpoint_url = ""
        else:
            self._endpoint_url = ""
            LOG.warning(
                "No explicit receiver endpoint available (glasses Wi-Fi IP "
                "unknown). Falling back to SDK mDNS discovery "
                "(oatmeal_server.local); if streaming never connects, pass "
                "--wifi-endpoint https://<host-ip>:%s",
                self.config.http_server_port,
            )

        if hasattr(streaming_config, "keep_streaming_on_disconnection"):
            # Official flag behind `aria_gen2 streaming start
            # --keep-streaming-on-disconnection`: without it the device stops
            # publishing when the control channel or Wi-Fi drops briefly.
            streaming_config.keep_streaming_on_disconnection = True

    @staticmethod
    def _host_ip_toward(remote_ip: str) -> str:
        """Local IP of the interface that routes towards remote_ip."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect((remote_ip, 9))
                return str(probe.getsockname()[0])
        except Exception as exc:
            LOG.warning("Could not determine host IP towards %s: %s", remote_ip, exc)
            return ""

    def _log_streaming_info(self) -> None:
        info = self._safe_call(getattr(self._device, "get_streaming_info", lambda: None), None)
        if info is None:
            return
        try:
            interface = getattr(info, "streaming_interface", None)
            if interface:
                self._active_interface = str(interface)
            LOG.info(
                "Device streaming info: is_streaming=%s profile=%s interface=%s",
                getattr(info, "is_streaming", None),
                getattr(info, "profile_name", None),
                interface,
            )
        except Exception:
            LOG.debug("Could not read streaming info", exc_info=True)

    def stop_streaming(self) -> None:
        with self._lock:
            if not self._streaming and self._stream_receiver is None:
                return
            device_stopped = True
            if self._device is not None and self._streaming:
                if not self._control_alive:
                    self._try_reconnect_control("stop streaming")
                try:
                    self._device.stop_streaming()
                except Exception:
                    device_stopped = False
                    LOG.exception("Failed to stop device streaming")
            if self._stream_receiver is not None:
                try:
                    self._stream_receiver.stop_server()
                except Exception:
                    LOG.exception("Failed to stop stream receiver")
            self._stream_receiver = None
            self._streaming = False
            self._publishing = None
            self._publisher_ip = ""
            if not device_stopped:
                message = (
                    "Receiver stopped, but the glasses could not be reached and "
                    "may still be streaming. Plug the USB cable back in and "
                    "press Stop again, or run: aria_gen2 streaming stop"
                )
                LOG.warning(message)
                self.state.logs.set(message)
            self._update_connection("Connected" if self._control_alive else "Control channel lost")

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
            if self.config.decode_rgb:
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
        if hasattr(stream_receiver, "register_device_calib_callback"):
            stream_receiver.register_device_calib_callback(self._device_calib_callback)

    def _device_calib_callback(self, calib_json: str, *args: Any) -> None:
        try:
            from projectaria_tools.core import calibration
            if isinstance(calib_json, str):
                self._device_calibration = calibration.device_calibration_from_json_string(calib_json)
        except Exception as exc:
            self.state.logs.set(f"Calibration parse failed: {exc}")

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
        if self.config.decode_rgb and time.monotonic() - self._last_rgb_success < 1.5:
            return
        camera_id = int(getattr(image_record, "camera_id", 0) or 0)
        if camera_id != self._preferred_slam_camera_id:
            return
        if not self._rgb_limiter.allow():
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
            self._store_video_frame("Camera Preview", arr, metadata)
            if not self._using_slam_fallback:
                self._using_slam_fallback = True
                self.state.logs.set("Camera preview active")
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
            # Only project real, currently-valid gaze; never draw an overlay
            # from stale or invalid angles.
            if rgb is not None and valid is not False:
                gaze_pt = project_gaze_to_rgb(
                    yaw, pitch, rgb.width, rgb.height, rgb.label,
                    calibration=getattr(self, "_device_calibration", None),
                    eyegaze_data=eyegaze_data
                )
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
                self._note_control_result(status is not None or bool(device_id))

                if not self._control_alive and self.config.connection_mode == "wifi":
                    self._maybe_reconnect_control()

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
                    self._absorb_device_status(status)
                    temp = self._finite_or_none(getattr(status, "skin_temp_celsius", None))
                    if temp is not None:
                        self.state.temperature.set(
                            self._temperature_sample(time.monotonic(), temp, "device skin")
                        )

                self._poll_receiver_connections()

                cpu = psutil.cpu_percent(interval=None) if psutil is not None else None
                ram = psutil.virtual_memory().percent if psutil is not None else None
                perf = PerformanceSample(
                    timestamp_s=time.monotonic(),
                    fps={k: v.value for k, v in self._fps.items()},
                    dropped_frames={k: v.dropped_frames for k, v in self._fps.items()},
                    overwrite_counts=self.state.buffer_overwrites(),
                    cpu_percent=cpu,
                    ram_percent=ram,
                    connection_state=self._connection_state_label(),
                    recording_state="ON" if is_recording else "OFF",
                )
                self.state.performance.set(perf)
                self._update_connection(
                    self._connection_state_label(),
                    device_id=device_id or self._device_serial,
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

    def _connection_state_label(self) -> str:
        if self._streaming:
            if not self._control_alive:
                return "Streaming (control channel lost)"
            return "Streaming"
        if not self._control_alive:
            return "Control channel lost"
        return "Connected"

    def _note_control_result(self, ok: bool) -> None:
        """Track control-channel health from device.status() outcomes.

        A few consecutive failures mean the DeviceClient link is gone — e.g.
        the USB cable was unplugged while streaming over Wi-Fi. Streaming is
        judged separately via the receiver, so this must not stop the stream.
        """
        if ok:
            if not self._control_alive:
                LOG.info("Control channel to the glasses is back")
                self.state.logs.set("Control channel restored")
            self._control_alive = True
            self._control_failures = 0
            return
        self._control_failures += 1
        if self._control_failures == 3 and self._control_alive:
            self._control_alive = False
            if self._streaming and self.config.connection_mode == "wifi":
                message = (
                    "Control channel lost (USB unplugged?). Wi-Fi streaming "
                    "continues; data below is still live from the receiver."
                )
            else:
                message = "Control channel to the glasses lost"
            LOG.warning(message)
            self.state.logs.set(message)

    def _maybe_reconnect_control(self, interval_s: float = 6.0) -> None:
        now = time.monotonic()
        if now - self._last_reconnect_attempt < interval_s:
            return
        self._last_reconnect_attempt = now
        self._try_reconnect_control("monitor")

    def _try_reconnect_control(self, reason: str) -> None:
        if self._device_client is None:
            return
        target_ip = self._device_ip
        try:
            if target_ip:
                LOG.info("Reconnecting control channel via %s (%s)", target_ip, reason)
                device = self._device_client.connect(
                    self._sdk_gen2.DeviceTarget(ip=target_ip)
                )
            else:
                LOG.info("Reconnecting control channel via USB discovery (%s)", reason)
                device = self._device_client.connect()
        except Exception as exc:
            LOG.debug("Control reconnect failed (%s): %s", reason, exc)
            return
        with self._lock:
            self._device = device
            if self.recording_manager is not None:
                self.recording_manager.set_device(device, self._sdk_gen2)
        self._note_control_result(True)

    def _absorb_device_status(self, status: Any) -> None:
        battery = getattr(status, "battery_level", None)
        try:
            self._battery_percent = int(battery) if battery is not None else None
        except Exception:
            self._battery_percent = None
        charging = getattr(status, "charging", None)
        self._charging = bool(charging) if charging is not None else None
        ssid = str(getattr(status, "wifi_ssid", "") or "")
        if ssid:
            self._wifi_ssid = ssid
        self._device_ip = str(getattr(status, "wifi_ip_address", "") or self._device_ip)

    def _poll_receiver_connections(self) -> None:
        """Receiver-side truth: is the device publishing to our HTTP server?

        AriaGen2HttpServer.connections() lists active device connections
        (device_serial, connection_id, client_ip); the SDK documents polling
        it to detect connect/reconnect/disconnect. This keeps working after
        the USB cable is unplugged, when device.status() no longer answers.
        """
        receiver = self._stream_receiver
        server = getattr(receiver, "server", None) if receiver is not None else None
        if server is None:
            return
        try:
            connections = server.connections()
        except Exception:
            return
        publishing = bool(connections)
        publisher_ip = ""
        if connections:
            first = connections[0]
            publisher_ip = str(first.get("client_ip", "") or "")
        if publishing != self._publishing:
            if publishing:
                LOG.info(
                    "Device connected to the receiver (serial=%s ip=%s)",
                    connections[0].get("device_serial", "?"),
                    publisher_ip or "?",
                )
                self.state.logs.set(
                    f"Receiving stream from the glasses ({publisher_ip or 'unknown ip'})"
                )
            elif self._publishing is not None:
                LOG.warning("Device disconnected from the receiver")
                self.state.logs.set(
                    "The glasses stopped publishing to the receiver. Waiting "
                    "for automatic reconnection..."
                )
        self._publishing = publishing
        self._publisher_ip = publisher_ip

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
                device_id=device_id or self._device_serial,
                device_ip=self._device_ip,
                sdk_version=self._sdk_version,
                status_message=message,
                profile_name=self.config.streaming_profile,
                # Battery/charging are live device readings: report them only
                # while the control channel actually answers, otherwise the UI
                # would show a stale value as current.
                battery_percent=self._battery_percent if self._control_alive else None,
                charging=self._charging if self._control_alive else None,
                wifi_ssid=self._wifi_ssid,
                streaming_interface=self._active_interface,
                batch_period_ms=self.config.effective_stream_batch_ms,
                control_alive=self._control_alive,
                publishing=self._publishing,
                publisher_ip=self._publisher_ip,
                endpoint_url=self._endpoint_url,
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
