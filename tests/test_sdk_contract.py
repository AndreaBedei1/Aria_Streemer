"""Contract tests against the really installed projectaria-client-sdk.

They run only where the SDK is available (Linux/macOS, e.g. the demo laptop
or WSL) and pin the API surface this app relies on for Wi-Fi streaming. If a
future SDK release renames or drops one of these members, these tests fail
before the app misbehaves in the field.
"""
from __future__ import annotations

from pathlib import Path

import pytest

sdk_gen2 = pytest.importorskip(
    "aria.sdk_gen2", reason="projectaria-client-sdk not installed on this platform"
)


def test_streaming_interfaces_exist():
    assert hasattr(sdk_gen2.StreamingInterface, "WIFI_STA")
    assert hasattr(sdk_gen2.StreamingInterface, "USB_NCM")


def test_http_streaming_config_supports_wifi_flow():
    config = sdk_gen2.HttpStreamingConfig()
    # Fields used by the Wi-Fi flow (batching, unplug survival, explicit URL).
    assert hasattr(config, "profile_name")
    assert hasattr(config, "streaming_interface")
    assert hasattr(config, "batch_period_ms")
    assert hasattr(config, "keep_streaming_on_disconnection")
    assert hasattr(config, "streaming_cert_name")
    endpoint = config.advanced_config.endpoint
    assert hasattr(endpoint, "url")
    assert hasattr(endpoint, "verify_server_certificates")
    # And they are assignable the way the worker assigns them.
    config.keep_streaming_on_disconnection = True
    config.batch_period_ms = 200
    endpoint.url = "https://192.168.1.10:6768"
    assert config.keep_streaming_on_disconnection is True


def test_device_status_reports_wifi_and_battery():
    # DeviceStatus instances are only produced by device.status(); the pybind
    # module does not export the class itself. The SDK type stubs are the
    # contract for its fields: check them so a rename shows up in CI.
    import aria

    stub = Path(aria.__file__).with_name("sdk_gen2.pyi")
    if not stub.exists():
        pytest.skip("sdk_gen2.pyi stub not shipped in this SDK build")
    text = stub.read_text(encoding="utf-8")
    assert hasattr(sdk_gen2.Device, "status")
    for field in (
        "battery_level",
        "charging",
        "wifi_connected",
        "wifi_ip_address",
        "wifi_ssid",
        "skin_temp_celsius",
    ):
        assert field in text, field


def test_device_exposes_streaming_state():
    for method in ("is_streaming", "get_streaming_info", "start_streaming", "stop_streaming"):
        assert hasattr(sdk_gen2.Device, method), method


def test_stream_receiver_exposes_server_connections():
    import aria.stream_receiver as receiver_module

    receiver = receiver_module.StreamReceiver(
        enable_image_decoding=False, enable_raw_stream=False
    )
    for method in (
        "set_server_config",
        "start_server",
        "stop_server",
        "register_rgb_callback",
        "register_slam_callback",
        "register_et_callback",
        "register_eye_gaze_callback",
        "register_hand_pose_callback",
        "register_ppg_callback",
        "register_barometer_callback",
    ):
        assert hasattr(receiver, method), method
    # Receiver-side connection tracking used to detect the USB unplug flow.
    assert hasattr(sdk_gen2.AriaGen2HttpServer, "connections")


def test_eye_gaze_has_no_pupil_fields():
    """Pupil diameter is not exposed by the live EyeGaze callback: the UI must
    keep showing N/A instead of inventing values."""
    from projectaria_tools.core.mps import EyeGaze

    attrs = dir(EyeGaze)
    assert not any("pupil_diameter" in a for a in attrs)
    for expected in ("yaw", "pitch", "depth", "combined_gaze_valid", "vergence"):
        assert expected in attrs
