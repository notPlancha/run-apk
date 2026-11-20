"""Tests for Android device and emulator management."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from run_apk.device import (
    DeviceInfo,
    boot_emulator,
    get_boot_status,
    list_avds,
    list_devices,
    resolve_device,
    wait_for_boot,
)


def test_list_devices():
    output = (
        "List of devices attached\n"
        "emulator-5554\tdevice\n"
        "192.168.1.100:5555\toffline\n"
        "PHYSICAL_SERIAL\tdevice\n"
    )
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=output, returncode=0)
        devices = list_devices(Path("adb"))

        assert len(devices) == 3
        assert devices[0] == DeviceInfo(serial="emulator-5554", state="device", is_emulator=True)
        assert devices[1] == DeviceInfo(
            serial="192.168.1.100:5555", state="offline", is_emulator=False
        )
        assert devices[2] == DeviceInfo(serial="PHYSICAL_SERIAL", state="device", is_emulator=False)


def test_list_avds():
    output = "Pixel_7_API_34\nPixel_6_API_33\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=output, returncode=0)
        avds = list_avds(Path("emulator"))
        assert avds == ["Pixel_7_API_34", "Pixel_6_API_33"]


def test_boot_emulator():
    with patch("subprocess.Popen") as mock_popen:
        boot_emulator(
            Path("emulator"),
            avd_name="Pixel_7_API_34",
            headless=True,
            wipe_data=True,
        )
        cmd = mock_popen.call_args[0][0]
        assert "emulator" in cmd[0]
        assert "-avd" in cmd
        assert "Pixel_7_API_34" in cmd
        assert "-no-window" in cmd
        assert "-wipe-data" in cmd


def test_get_boot_status():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="1\n", returncode=0)
        assert get_boot_status(Path("adb"), "emulator-5554") is True

        mock_run.return_value = MagicMock(stdout="0\n", returncode=0)
        assert get_boot_status(Path("adb"), "emulator-5554") is False


def test_wait_for_boot_success():
    with patch("run_apk.device.get_boot_status", side_effect=[False, True]), patch("time.sleep"):
        serial = wait_for_boot(Path("adb"), serial="emulator-5554", timeout=10, poll_interval=0.1)
        assert serial == "emulator-5554"


def test_wait_for_boot_timeout():
    with patch("run_apk.device.get_boot_status", return_value=False), patch("time.sleep"):
        with pytest.raises(TimeoutError, match="failed to complete boot"):
            wait_for_boot(Path("adb"), serial="emulator-5554", timeout=0.01, poll_interval=0.01)


def test_resolve_device_explicit_serial():
    devs = [DeviceInfo("emulator-5554", "device", True)]
    with patch("run_apk.device.list_devices", return_value=devs):
        serial = resolve_device(Path("adb"), Path("emulator"), device_serial="emulator-5554")
        assert serial == "emulator-5554"


def test_resolve_device_existing_active():
    devs = [DeviceInfo("emulator-5554", "device", True)]
    with patch("run_apk.device.list_devices", return_value=devs):
        serial = resolve_device(Path("adb"), Path("emulator"))
        assert serial == "emulator-5554"


def test_resolve_device_boot_avd():
    with (
        patch("run_apk.device.list_devices", return_value=[]),
        patch("run_apk.device.list_avds", return_value=["Pixel_7"]),
        patch("run_apk.device.boot_emulator") as mock_boot,
        patch("run_apk.device.wait_for_boot", return_value="emulator-5554"),
    ):
        serial = resolve_device(Path("adb"), Path("emulator"), avd_name="Pixel_7")
        assert serial == "emulator-5554"
        mock_boot.assert_called_once()


def test_resolve_device_no_avds():
    with (
        patch("run_apk.device.list_devices", return_value=[]),
        patch("run_apk.device.list_avds", return_value=[]),
    ):
        with pytest.raises(RuntimeError, match="no AVDs"):
            resolve_device(Path("adb"), Path("emulator"))
