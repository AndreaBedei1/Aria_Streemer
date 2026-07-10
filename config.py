from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_RECORDING_PROFILE = "driver_dataset_v1_raw_for_ht"
DEFAULT_STREAMING_PROFILE = "mp_streaming_demo"

# Batch period defaults per interface. USB keeps the historical 20 ms value;
# Wi-Fi follows the official Aria Gen 2 guidance (>=200 ms for wireless
# streaming to limit thermal load and radio congestion).
DEFAULT_USB_BATCH_MS = 20
DEFAULT_WIFI_BATCH_MS = 200


@dataclass
class AppConfig:
    connection_mode: str = "usb"
    mock: bool = False
    rgb_fps: int = 10
    ht_fps: int = 10
    et_fps: int = 5
    hr_update_hz: float = 1.0
    rgb_width: int = 960
    rgb_height: int = 540
    output_dir: str = "./recordings"
    debug_streams: bool = False
    debug_image_dump: str = ""
    decode_rgb: bool = True
    stream_batch_ms: Optional[int] = None
    streaming_profile: str = DEFAULT_STREAMING_PROFILE
    recording_profile: str = DEFAULT_RECORDING_PROFILE
    device_ip: str = ""
    wifi_endpoint_url: str = ""
    http_server_port: int = 6768
    temperature_warning_c: float = 45.0
    ui_refresh_hz: int = 30
    ppg_sample_rate_hz: float = 256.0

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir).expanduser().resolve()

    @property
    def effective_stream_batch_ms(self) -> int:
        """Batch period actually sent to the device.

        Explicit --stream-batch-ms always wins. Otherwise USB keeps the
        historical low-latency default while Wi-Fi uses the official
        wireless recommendation.
        """
        if self.stream_batch_ms is not None:
            return self.stream_batch_ms
        if self.connection_mode == "wifi":
            return DEFAULT_WIFI_BATCH_MS
        return DEFAULT_USB_BATCH_MS


def parse_args() -> AppConfig:
    parser = argparse.ArgumentParser(
        description="Lightweight Project Aria Gen 2 realtime dashboard"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--usb", action="store_true", help="Use USB_NCM streaming")
    group.add_argument("--wifi", action="store_true", help="Use WIFI_STA streaming")
    parser.add_argument("--mock", action="store_true", help="Run without glasses")
    parser.add_argument("--rgb-fps", type=int, default=10)
    parser.add_argument("--ht-fps", type=int, default=10)
    parser.add_argument("--et-fps", type=int, default=5)
    parser.add_argument("--hr-update-hz", type=float, default=1.0)
    parser.add_argument("--rgb-width", type=int, default=960)
    parser.add_argument("--rgb-height", type=int, default=540)
    parser.add_argument("--output-dir", type=str, default="./recordings")
    parser.add_argument("--debug-streams", action="store_true")
    parser.add_argument(
        "--decode-rgb",
        action="store_true",
        default=True,
        help="Decode the RGB H265 stream. Higher latency; off by default for demos.",
    )
    parser.add_argument(
        "--stream-batch-ms",
        type=int,
        default=None,
        help=(
            "HTTP streaming batch period in ms. Default: 20 for USB, 200 for "
            "Wi-Fi (official wireless recommendation). Lower values reduce "
            "latency but increase device heat over Wi-Fi."
        ),
    )
    parser.add_argument(
        "--device-ip",
        type=str,
        default="",
        help=(
            "Glasses IP for Wi-Fi control connection. Overrides the "
            "ARIA_DEVICE_IP environment variable."
        ),
    )
    parser.add_argument(
        "--wifi-endpoint",
        type=str,
        default="",
        help=(
            "Explicit receiver URL the glasses should stream to over Wi-Fi, "
            "e.g. https://192.168.1.10:6768. Default: auto-detected host IP, "
            "falling back to the SDK mDNS name (oatmeal_server.local)."
        ),
    )
    parser.add_argument(
        "--debug-image-dump",
        type=str,
        default="",
        help="Save first GUI image frames and metadata to this directory",
    )
    args = parser.parse_args()
    mode = "wifi" if args.wifi else "usb"
    device_ip = args.device_ip or os.getenv("ARIA_DEVICE_IP", "")

    return AppConfig(
        connection_mode=mode,
        mock=args.mock,
        rgb_fps=max(1, args.rgb_fps),
        ht_fps=max(1, args.ht_fps),
        et_fps=max(1, args.et_fps),
        hr_update_hz=max(0.2, args.hr_update_hz),
        rgb_width=max(160, args.rgb_width),
        rgb_height=max(120, args.rgb_height),
        output_dir=args.output_dir,
        debug_streams=args.debug_streams,
        debug_image_dump=args.debug_image_dump,
        decode_rgb=args.decode_rgb,
        stream_batch_ms=None if args.stream_batch_ms is None else max(5, args.stream_batch_ms),
        device_ip=device_ip,
        wifi_endpoint_url=args.wifi_endpoint.strip(),
    )
