#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from processing.image_conversion import (  # noqa: E402
    _ensure_uint8_rgb,
    assess_display_quality,
    conversion_candidates,
    normalize_image_for_display,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dump Project Aria Gen 2 image streams to PNG/JSON for debugging."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--usb", action="store_true", help="Use USB_NCM streaming")
    mode.add_argument("--wifi", action="store_true", help="Use WIFI_STA streaming")
    parser.add_argument("--profile", default="mp_streaming_demo")
    parser.add_argument("--out", default="/tmp/aria_frame_debug")
    parser.add_argument("--max-frames", type=int, default=20)
    parser.add_argument("--timeout-s", type=float, default=18.0)
    parser.add_argument("--port", type=int, default=6768)
    parser.add_argument("--device-ip", default=os.getenv("ARIA_DEVICE_IP", ""))
    return parser.parse_args()


def save_rgb_png(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import cv2

        if cv2.imwrite(str(path), rgb[:, :, ::-1]):
            return
    except Exception:
        pass
    from PIL import Image

    Image.fromarray(rgb).save(path)


def public_attrs(obj: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if obj is None:
        return out
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            value = getattr(obj, name)
        except Exception:
            continue
        if callable(value):
            continue
        if isinstance(value, np.generic):
            value = value.item()
        out[name] = value
    return out


def local_streaming_cert_name() -> str:
    cert_name_path = Path("~/.aria/streaming-certs/persistent/publisher-cert-name").expanduser()
    try:
        return cert_name_path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def extract_array(image_data: Any) -> np.ndarray:
    if hasattr(image_data, "to_numpy_array"):
        return np.asarray(image_data.to_numpy_array())
    return np.asarray(image_data)


class ImageDumpSession:
    def __init__(self, out_dir: Path, max_frames: int):
        self.out_dir = out_dir
        self.max_frames = max(1, max_frames)
        self.counts = {"RGB": 0, "SLAM": 0, "ET": 0}
        self.accepted = {"RGB": 0, "SLAM": 0, "ET": 0}
        self.lock = threading.Lock()
        self.first_frame_at = 0.0

    def callback(self, source_name: str):
        def _callback(image_data: Any, image_record: Any, *args: Any) -> None:
            with self.lock:
                index = self.counts[source_name]
                if index >= self.max_frames:
                    return
                self.counts[source_name] = index + 1
                if self.first_frame_at <= 0.0:
                    self.first_frame_at = time.monotonic()

            try:
                raw = extract_array(image_data)
                rgb, metadata = normalize_image_for_display(
                    raw, image_record, source_name=source_name
                )
            except Exception as exc:
                metadata = {
                    "source_name": source_name,
                    "valid": False,
                    "error": str(exc),
                    "warning": "conversion failed",
                }
                rgb = np.zeros((64, 64, 3), dtype=np.uint8)
                raw = rgb

            metadata["accepted"] = bool(metadata.get("valid", False))
            metadata["record_attrs"] = public_attrs(image_record)
            metadata["received_at_monotonic_s"] = time.monotonic()
            metadata["callback_extra_args"] = [str(arg) for arg in args]

            camera_id = metadata.get("camera_id")
            prefix = (
                self.out_dir
                / source_name.lower()
                / f"{source_name.lower()}_{camera_id or 'unknown'}_{index:03d}"
            )
            save_rgb_png(prefix.with_name(prefix.name + "_converted.png"), rgb)
            self._save_candidates(prefix, raw)
            with prefix.with_suffix(".json").open("w", encoding="utf-8") as handle:
                json.dump(metadata, handle, indent=2, default=str)

            if metadata["accepted"]:
                with self.lock:
                    self.accepted[source_name] += 1

            stats = {
                "camera_id": metadata.get("camera_id"),
                "frame_number": metadata.get("frame_number"),
                "timestamp": metadata.get("capture_timestamp_ns"),
                "shape": metadata.get("original_shape"),
                "dtype": metadata.get("original_dtype"),
                "min": metadata.get("original_min"),
                "max": metadata.get("original_max"),
                "mean": metadata.get("original_mean"),
                "std": metadata.get("original_std"),
                "path": metadata.get("conversion_path"),
                "quality": metadata.get("quality_score"),
                "yellow_fraction": metadata.get("yellow_fraction"),
                "accepted": metadata.get("accepted"),
                "warning": metadata.get("warning") or metadata.get("error"),
            }
            print(f"{source_name} frame {index:03d}: {json.dumps(stats, default=str)}", flush=True)

        return _callback

    def _save_candidates(self, prefix: Path, raw: np.ndarray) -> None:
        try:
            candidates = conversion_candidates(raw)
        except Exception:
            return
        for name, candidate in candidates:
            try:
                candidate_rgb = _ensure_uint8_rgb(candidate)
                quality = assess_display_quality(candidate_rgb, source_is_et=prefix.parent.name == "et")
                candidate_path = prefix.with_name(prefix.name + f"_{name}.png")
                save_rgb_png(candidate_path, candidate_rgb)
                with candidate_path.with_suffix(".json").open("w", encoding="utf-8") as handle:
                    json.dump(quality, handle, indent=2, default=str)
            except Exception:
                continue

    def primary_done(self) -> bool:
        with self.lock:
            return self.counts["RGB"] >= self.max_frames or self.counts["SLAM"] >= self.max_frames

    def accepted_total(self) -> int:
        with self.lock:
            return sum(self.accepted.values())

    def summary(self) -> dict[str, Any]:
        with self.lock:
            return {"counts": dict(self.counts), "accepted": dict(self.accepted)}


def connect_device(sdk_gen2: Any, args: argparse.Namespace):
    client = sdk_gen2.DeviceClient()
    client_config = sdk_gen2.DeviceClientConfig()
    client.set_client_config(client_config)

    if args.device_ip:
        try:
            device = client.connect(sdk_gen2.DeviceTarget(ip=args.device_ip))
        except Exception as exc:
            print(f"IP connect failed ({exc}); trying SDK default discovery")
            device = client.connect()
    else:
        device = client.connect()

    streaming_config = sdk_gen2.HttpStreamingConfig()
    streaming_config.profile_name = args.profile
    cert_name = local_streaming_cert_name()
    if cert_name and hasattr(streaming_config, "streaming_cert_name"):
        streaming_config.streaming_cert_name = cert_name
    if hasattr(streaming_config, "streaming_interface"):
        streaming_config.streaming_interface = (
            sdk_gen2.StreamingInterface.WIFI_STA if args.wifi else sdk_gen2.StreamingInterface.USB_NCM
        )
    try:
        streaming_config.advanced_config.endpoint.verify_server_certificates = False
    except Exception:
        pass

    device.set_streaming_config(streaming_config)
    return client, device


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    import aria.sdk_gen2 as sdk_gen2
    import aria.stream_receiver as receiver

    try:
        sdk_version = importlib.metadata.version("projectaria-client-sdk")
    except Exception:
        sdk_version = "unknown"
    print(f"Project Aria Client SDK version: {sdk_version}")
    print(f"Mode: {'wifi' if args.wifi else 'usb'} profile={args.profile} out={out_dir}")

    client = None
    device = None
    stream_receiver = None
    session = ImageDumpSession(out_dir, args.max_frames)
    try:
        client, device = connect_device(sdk_gen2, args)
        print(f"Connected device: {safe_call(device.serial, safe_call(device.connection_id, 'unknown'))}")
        status = safe_call(device.status, None)
        if status is not None:
            print(f"Device status: {json.dumps(public_attrs(status), default=str)}")

        server_config = sdk_gen2.HttpServerConfig()
        server_config.address = "0.0.0.0"
        server_config.port = args.port
        stream_receiver = receiver.StreamReceiver(
            enable_image_decoding=True, enable_raw_stream=False
        )
        stream_receiver.set_server_config(server_config)
        for setter in ("set_rgb_queue_size", "set_slam_queue_size", "set_et_queue_size"):
            if hasattr(stream_receiver, setter):
                getattr(stream_receiver, setter)(1)
        stream_receiver.register_rgb_callback(session.callback("RGB"))
        stream_receiver.register_slam_callback(session.callback("SLAM"))
        stream_receiver.register_et_callback(session.callback("ET"))

        print("Starting public StreamReceiver server...")
        stream_receiver.start_server()
        print("Starting device streaming...")
        device.start_streaming()

        started = time.monotonic()
        while time.monotonic() - started < args.timeout_s:
            if session.primary_done() and time.monotonic() - started > 6.0:
                break
            time.sleep(0.1)
    finally:
        if device is not None:
            try:
                device.stop_streaming()
            except Exception as exc:
                print(f"Warning: failed to stop device streaming: {exc}")
        if stream_receiver is not None:
            try:
                stream_receiver.stop_server()
            except Exception as exc:
                print(f"Warning: failed to stop StreamReceiver: {exc}")
        if client is not None and device is not None:
            try:
                client.disconnect(device)
            except Exception:
                pass

    summary = session.summary()
    print(f"Summary: {json.dumps(summary)}")
    print(f"Debug files written under: {out_dir}")
    if session.accepted_total() <= 0:
        print("FAILED: no valid RGB/SLAM/ET image frame was accepted")
        return 2
    return 0


def safe_call(func: Any, default: Any) -> Any:
    try:
        return func()
    except Exception:
        return default


if __name__ == "__main__":
    raise SystemExit(main())
