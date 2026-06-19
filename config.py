from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_RECORDING_PROFILE = "driver_dataset_v1_raw_for_ht"
DEFAULT_STREAMING_PROFILE = "mp_streaming_demo"


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
    force_rgb_decode: bool = False
    streaming_profile: str = DEFAULT_STREAMING_PROFILE
    recording_profile: str = DEFAULT_RECORDING_PROFILE
    device_ip: str = ""
    http_server_port: int = 6768
    temperature_warning_c: float = 45.0
    ui_refresh_hz: int = 30
    ppg_sample_rate_hz: float = 256.0

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir).expanduser().resolve()


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
        "--force-rgb-decode",
        action="store_true",
        help="Try the real RGB H265 decoder instead of the stable SLAM preview",
    )

    args = parser.parse_args()
    mode = "wifi" if args.wifi else "usb"
    device_ip = os.getenv("ARIA_DEVICE_IP", "")

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
        force_rgb_decode=args.force_rgb_decode,
        device_ip=device_ip,
    )
