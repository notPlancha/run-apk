"""Tests for APK installation, launching, screenshots, and logcat streaming."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from run_apk.runner import (
    install_apk,
    launch_app,
    stream_logcat,
    take_screenshot,
)


def test_install_apk_success(tmp_path: Path):
    apk = tmp_path / "app.apk"
    apk.write_text("data")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Success\n", stderr="")
        install_apk(Path("adb"), "emulator-5554", apk)

        cmd = mock_run.call_args[0][0]
        assert "adb" in cmd[0]
        assert "install" in cmd
        assert "emulator-5554" in cmd
        assert str(apk) in cmd


def test_install_apk_failure(tmp_path: Path):
    apk = tmp_path / "app.apk"
    apk.write_text("data")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="INSTALL_FAILED_ALREADY_EXISTS"
        )
        with pytest.raises(RuntimeError, match="Failed to install APK"):
            install_apk(Path("adb"), "emulator-5554", apk)


def test_launch_app_activity_success():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Starting: Intent ...", stderr="")
        launch_app(Path("adb"), "emulator-5554", "com.example.app", "MainActivity")

        cmd = mock_run.call_args[0][0]
        assert "am" in cmd
        assert "start" in cmd
        assert "com.example.app/MainActivity" in cmd


def test_launch_app_activity_fallback_to_monkey():
    with patch("subprocess.run") as mock_run:
        # First call (am start) fails, second call (monkey) succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="Error: Activity class does not exist", stderr=""),
            MagicMock(returncode=0, stdout="Events injected: 1", stderr=""),
        ]
        launch_app(Path("adb"), "emulator-5554", "com.example.app", "BadActivity")

        assert mock_run.call_count == 2
        second_cmd = mock_run.call_args_list[1][0][0]
        assert "monkey" in second_cmd


def test_launch_app_no_activity_monkey():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Events injected: 1", stderr="")
        launch_app(Path("adb"), "emulator-5554", "com.example.app", None)

        cmd = mock_run.call_args[0][0]
        assert "monkey" in cmd
        assert "com.example.app" in cmd


def test_take_screenshot(tmp_path: Path):
    output_path = tmp_path / "screenshots" / "shot.png"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        saved = take_screenshot(Path("adb"), "emulator-5554", output_path)

        assert saved == output_path.resolve()
        assert mock_run.call_count == 3
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any("screencap" in c for c in calls)
        assert any("pull" in c for c in calls)
        assert any("rm" in c for c in calls)


def test_stream_logcat():
    with patch("subprocess.Popen") as mock_popen, patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="1234\n")
        proc_mock = MagicMock()
        proc_mock.stdout = ["01-01 12:00:00.000 1234 1234 D App: Hello World\n"]
        proc_mock.poll.return_value = 0
        mock_popen.return_value = proc_mock

        stream_logcat(Path("adb"), "emulator-5554", package_name="com.example.app")
        mock_popen.assert_called_once()
