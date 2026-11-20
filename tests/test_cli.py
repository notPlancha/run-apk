"""Tests for run-apk CLI command execution."""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from run_apk import __version__
from run_apk.apk import ApkInfo
from run_apk.cli import app
from run_apk.sdk import AndroidTools

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_cli_help():
    result = runner.invoke(app, ["--help"], prog_name="run-apk")
    assert result.exit_code == 0
    assert "run-apk" in result.stdout
    assert "--avd" in result.stdout
    assert "--device" in result.stdout
    assert "--headless" in result.stdout
    assert "--no-launch" in result.stdout
    assert "--wipe-data" in result.stdout
    assert "--screenshot" in result.stdout
    assert "--logcat" in result.stdout


def test_cli_run_full_flow(tmp_path: Path):
    fake_apk = tmp_path / "test.apk"
    fake_apk.write_text("apk dummy content")

    mock_tools = AndroidTools(
        sdk_root=tmp_path,
        adb=tmp_path / "adb",
        emulator=tmp_path / "emulator",
        aapt2=None,
    )
    mock_apk_info = ApkInfo(
        package_name="com.test.cli",
        version_name="1.0.0",
        version_code=1,
        main_activity="com.test.cli.MainActivity",
    )

    with (
        patch("run_apk.cli.discover_tools", return_value=mock_tools),
        patch("run_apk.cli.inspect_apk", return_value=mock_apk_info),
        patch("run_apk.cli.resolve_device", return_value="emulator-5554") as mock_resolve,
        patch("run_apk.cli.install_apk") as mock_install,
        patch("run_apk.cli.launch_app") as mock_launch,
    ):
        result = runner.invoke(app, [str(fake_apk)])

        assert result.exit_code == 0
        mock_resolve.assert_called_once_with(
            adb_path=mock_tools.adb,
            emulator_path=mock_tools.emulator,
            device_serial=None,
            avd_name=None,
            headless=False,
            wipe_data=False,
        )
        mock_install.assert_called_once_with(
            adb_path=mock_tools.adb,
            serial="emulator-5554",
            apk_path=fake_apk.resolve(),
        )
        mock_launch.assert_called_once_with(
            adb_path=mock_tools.adb,
            serial="emulator-5554",
            package_name="com.test.cli",
            activity_name="com.test.cli.MainActivity",
        )


def test_cli_run_with_flags(tmp_path: Path):
    fake_apk = tmp_path / "test.apk"
    fake_apk.write_text("apk dummy content")
    screenshot_file = tmp_path / "shot.png"

    mock_tools = AndroidTools(
        sdk_root=tmp_path,
        adb=tmp_path / "adb",
        emulator=tmp_path / "emulator",
        aapt2=None,
    )
    mock_apk_info = ApkInfo(
        package_name="com.test.cli",
        version_name="1.0.0",
        version_code=1,
        main_activity="com.test.cli.MainActivity",
    )

    with (
        patch("run_apk.cli.discover_tools", return_value=mock_tools),
        patch("run_apk.cli.inspect_apk", return_value=mock_apk_info),
        patch("run_apk.cli.resolve_device", return_value="emulator-5554") as mock_resolve,
        patch("run_apk.cli.install_apk"),
        patch("run_apk.cli.launch_app") as mock_launch,
        patch("run_apk.cli.take_screenshot") as mock_screenshot,
        patch("run_apk.cli.stream_logcat") as mock_logcat,
        patch("run_apk.cli.time.sleep"),
    ):
        result = runner.invoke(
            app,
            [
                str(fake_apk),
                "--avd",
                "Pixel_7",
                "--headless",
                "--no-launch",
                "--wipe-data",
                "--screenshot",
                str(screenshot_file),
                "--logcat",
            ],
        )

        assert result.exit_code == 0
        mock_resolve.assert_called_once_with(
            adb_path=mock_tools.adb,
            emulator_path=mock_tools.emulator,
            device_serial=None,
            avd_name="Pixel_7",
            headless=True,
            wipe_data=True,
        )
        # --no-launch flag was set
        mock_launch.assert_not_called()
        mock_screenshot.assert_called_once()
        mock_logcat.assert_called_once()


def test_cli_missing_apk():
    result = runner.invoke(app, ["non_existent.apk"])
    assert result.exit_code != 0
