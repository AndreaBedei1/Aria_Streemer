"""Wi-Fi streaming behaviour of AriaStreamWorker, exercised with a fake SDK.

These tests mirror the official Aria Gen 2 flow (aria_gen2 streaming start
--interface wifi_sta --batch-period-ms 200, unplug the USB cable afterwards)
and pin down that the USB path keeps its historical configuration.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aria_stream_worker import AriaStreamWorker
from config import AppConfig
from stream_state import SharedStreamState


class FakeEndpoint:
    def __init__(self):
        self.url = ""
        self.verify_server_certificates = True


class FakeAdvancedConfig:
    def __init__(self):
        self.endpoint = FakeEndpoint()


class FakeHttpStreamingConfig:
    def __init__(self):
        self.profile_name = ""
        self.streaming_cert_name = ""
        self.streaming_interface = None
        self.batch_period_ms = 0
        self.keep_streaming_on_disconnection = False
        self.advanced_config = FakeAdvancedConfig()


class FakeHttpServerConfig:
    def __init__(self):
        self.address = ""
        self.port = 0
        self.use_ssl = True


class FakeDeviceTarget:
    def __init__(self, ip: str = "", serial: str = ""):
        self.ip = ip
        self.serial = serial


class FakeDeviceClientConfig:
    pass


class FakeStatus:
    def __init__(self, wifi_connected: bool = True):
        self.battery_level = 87
        self.charging = True
        self.charger_connected = True
        self.wifi_enabled = True
        self.wifi_configured = True
        self.wifi_connected = wifi_connected
        self.wifi_ip_address = "192.168.1.42" if wifi_connected else ""
        self.wifi_ssid = "LabNet" if wifi_connected else ""
        self.skin_temp_celsius = 33.5
        self.device_mode = "partner"


class FakeDevice:
    def __init__(self, status: FakeStatus, already_streaming: bool = False):
        self._status = status
        self._already_streaming = already_streaming
        self.streaming_config = None
        self.start_calls = 0
        self.stop_calls = 0
        self.fail_stop = False

    def connection_id(self):
        return "fake-connection"

    def serial(self):
        return "FAKE-SERIAL-01"

    def status(self):
        return self._status

    def set_streaming_config(self, config):
        self.streaming_config = config

    def is_streaming(self):
        return self._already_streaming

    def start_streaming(self):
        self.start_calls += 1

    def stop_streaming(self):
        self.stop_calls += 1
        if self.fail_stop:
            raise RuntimeError("device unreachable")

    def is_recording(self):
        return False

    def device_profiles(self):
        return {}


class FakeDeviceClient:
    def __init__(self, device: FakeDevice):
        self._device = device
        self.connect_targets = []

    def set_client_config(self, config):
        pass

    def connect(self, target=None):
        self.connect_targets.append(target)
        return self._device

    def disconnect(self, device):
        pass


class FakeServer:
    def __init__(self):
        self.connection_rows = []

    def connections(self):
        return self.connection_rows


class FakeStreamReceiver:
    def __init__(self, enable_image_decoding=True, enable_raw_stream=False):
        self.enable_image_decoding = enable_image_decoding
        self.server_config = None
        self.server = FakeServer()
        self.started = 0
        self.stopped = 0
        self.callbacks = {}

    def set_server_config(self, config):
        self.server_config = config

    def start_server(self):
        self.started += 1
        return self.server

    def stop_server(self):
        self.stopped += 1

    def _register(self, name, callback):
        self.callbacks[name] = callback

    def register_rgb_callback(self, cb):
        self._register("rgb", cb)

    def register_slam_callback(self, cb):
        self._register("slam", cb)

    def register_et_callback(self, cb):
        self._register("et", cb)

    def register_eye_gaze_callback(self, cb):
        self._register("eye_gaze", cb)

    def register_hand_pose_callback(self, cb):
        self._register("hand_pose", cb)

    def register_ppg_callback(self, cb):
        self._register("ppg", cb)

    def register_barometer_callback(self, cb):
        self._register("barometer", cb)

    def register_device_calib_callback(self, cb):
        self._register("device_calib", cb)

    def set_rgb_queue_size(self, size):
        pass

    def set_slam_queue_size(self, size):
        pass

    def set_et_queue_size(self, size):
        pass

    def set_eye_gaze_queue_size(self, size):
        pass

    def set_hand_pose_queue_size(self, size):
        pass

    def set_vio_queue_size(self, size):
        pass


def make_fake_sdk(device: FakeDevice):
    sdk = types.SimpleNamespace()
    sdk.DeviceClient = lambda: FakeDeviceClient(device)
    sdk.DeviceClientConfig = FakeDeviceClientConfig
    sdk.DeviceTarget = FakeDeviceTarget
    sdk.HttpStreamingConfig = FakeHttpStreamingConfig
    sdk.HttpServerConfig = FakeHttpServerConfig
    sdk.StreamingInterface = types.SimpleNamespace(
        WIFI_STA="WIFI_STA", USB_NCM="USB_NCM", WIFI_SAP="WIFI_SAP", USB_RNDIS="USB_RNDIS"
    )
    receiver_module = types.SimpleNamespace(StreamReceiver=FakeStreamReceiver)
    return sdk, receiver_module


def make_worker(monkeypatch, mode: str, device: FakeDevice, cert_name: str = ""):
    config = AppConfig(connection_mode=mode, mock=False)
    state = SharedStreamState()
    worker = AriaStreamWorker(config, state)
    sdk, receiver_module = make_fake_sdk(device)

    def fake_import():
        worker._sdk_gen2 = sdk
        worker._receiver_module = receiver_module
        worker._sdk_version = "fake-2.4.0"

    monkeypatch.setattr(worker, "_import_sdk", fake_import)
    monkeypatch.setattr(worker, "_start_monitor", lambda: None)
    monkeypatch.setattr(
        AriaStreamWorker, "_local_streaming_cert_name", staticmethod(lambda: cert_name)
    )
    monkeypatch.setattr(
        AriaStreamWorker, "_host_ip_toward", staticmethod(lambda remote: "10.0.0.5")
    )
    return worker, state


def test_wifi_config_follows_official_flow(monkeypatch):
    device = FakeDevice(FakeStatus(wifi_connected=True))
    worker, _ = make_worker(monkeypatch, "wifi", device)
    worker.connect()
    worker.start_streaming()

    cfg = device.streaming_config
    assert cfg is not None
    assert cfg.streaming_interface == "WIFI_STA"
    # Official wireless recommendation from the Aria Gen 2 docs.
    assert cfg.batch_period_ms == 200
    # Required for the "start over USB, then unplug the cable" flow.
    assert cfg.keep_streaming_on_disconnection is True
    # Explicit receiver endpoint on the host interface facing the glasses:
    # no local certs in this test, so plain http.
    assert cfg.advanced_config.endpoint.url == "http://10.0.0.5:6768"
    assert device.start_calls == 1
    assert worker.streaming


def test_wifi_uses_https_when_certs_installed(monkeypatch):
    device = FakeDevice(FakeStatus(wifi_connected=True))
    worker, _ = make_worker(monkeypatch, "wifi", device, cert_name="persistent-cert")
    worker.connect()
    worker.start_streaming()

    cfg = device.streaming_config
    assert cfg.streaming_cert_name == "persistent-cert"
    assert cfg.advanced_config.endpoint.url == "https://10.0.0.5:6768"


def test_wifi_endpoint_override_wins(monkeypatch):
    device = FakeDevice(FakeStatus(wifi_connected=True))
    config = AppConfig(
        connection_mode="wifi", wifi_endpoint_url="https://192.168.7.7:6768"
    )
    state = SharedStreamState()
    worker = AriaStreamWorker(config, state)
    sdk, receiver_module = make_fake_sdk(device)

    def fake_import():
        worker._sdk_gen2 = sdk
        worker._receiver_module = receiver_module

    monkeypatch.setattr(worker, "_import_sdk", fake_import)
    monkeypatch.setattr(worker, "_start_monitor", lambda: None)
    monkeypatch.setattr(
        AriaStreamWorker, "_local_streaming_cert_name", staticmethod(lambda: "")
    )
    worker.connect()
    worker.start_streaming()
    assert device.streaming_config.advanced_config.endpoint.url == "https://192.168.7.7:6768"


def test_usb_config_unchanged(monkeypatch):
    device = FakeDevice(FakeStatus(wifi_connected=True))
    worker, _ = make_worker(monkeypatch, "usb", device)
    worker.connect()
    worker.start_streaming()

    cfg = device.streaming_config
    assert cfg.streaming_interface == "USB_NCM"
    # Historical USB default: low-latency 20 ms batching.
    assert cfg.batch_period_ms == 20
    # USB path must stay untouched: no keep flag, no explicit endpoint.
    assert cfg.keep_streaming_on_disconnection is False
    assert cfg.advanced_config.endpoint.url == ""


def test_wifi_requires_glasses_on_wifi(monkeypatch):
    device = FakeDevice(FakeStatus(wifi_connected=False))
    worker, _ = make_worker(monkeypatch, "wifi", device)
    worker.connect()
    with pytest.raises(RuntimeError, match="wifi connect"):
        worker.start_streaming()
    assert device.start_calls == 0
    assert not worker.streaming


def test_attach_to_already_streaming_device(monkeypatch):
    device = FakeDevice(FakeStatus(wifi_connected=True), already_streaming=True)
    worker, state = make_worker(monkeypatch, "wifi", device)
    worker.connect()
    worker.start_streaming()
    # The device session started elsewhere (e.g. aria_gen2 CLI): attach the
    # receiver without calling start_streaming again.
    assert device.start_calls == 0
    assert worker.streaming


def test_stop_streaming_survives_unreachable_device(monkeypatch):
    device = FakeDevice(FakeStatus(wifi_connected=True))
    device.fail_stop = True
    worker, state = make_worker(monkeypatch, "wifi", device)
    worker.connect()
    worker.start_streaming()
    receiver = worker._stream_receiver
    worker.stop_streaming()

    assert receiver.stopped == 1
    assert not worker.streaming
    assert "aria_gen2 streaming stop" in (state.logs.get() or "")


def test_control_loss_and_recovery(monkeypatch):
    device = FakeDevice(FakeStatus(wifi_connected=True))
    worker, state = make_worker(monkeypatch, "wifi", device)
    worker.connect()
    worker.start_streaming()

    for _ in range(3):
        worker._note_control_result(False)
    assert worker._control_alive is False
    assert "control" in (state.logs.get() or "").lower()
    assert worker._connection_state_label() == "Streaming (control channel lost)"

    worker._note_control_result(True)
    assert worker._control_alive is True
    assert worker._connection_state_label() == "Streaming"


def test_receiver_connections_drive_publishing_state(monkeypatch):
    device = FakeDevice(FakeStatus(wifi_connected=True))
    worker, state = make_worker(monkeypatch, "wifi", device)
    worker.connect()
    worker.start_streaming()

    server = worker._stream_receiver.server
    server.connection_rows = [
        {"device_serial": "FAKE-SERIAL-01", "connection_id": "c1", "client_ip": "192.168.1.42"}
    ]
    worker._poll_receiver_connections()
    assert worker._publishing is True
    assert worker._publisher_ip == "192.168.1.42"

    server.connection_rows = []
    worker._poll_receiver_connections()
    assert worker._publishing is False


def test_host_ip_toward_loopback():
    ip = AriaStreamWorker._host_ip_toward("127.0.0.1")
    assert ip == "127.0.0.1"


def test_connection_sample_carries_wifi_telemetry(monkeypatch):
    device = FakeDevice(FakeStatus(wifi_connected=True))
    worker, state = make_worker(monkeypatch, "wifi", device)
    worker.connect()
    worker.start_streaming()

    sample = state.connection.get()
    assert sample is not None
    assert sample.mode == "wifi"
    assert sample.streaming_interface == "WIFI_STA"
    assert sample.batch_period_ms == 200
    assert sample.battery_percent == 87
    assert sample.wifi_ssid == "LabNet"
    assert sample.endpoint_url == "http://10.0.0.5:6768"
