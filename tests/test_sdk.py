"""Tests for Android SDK and tool discovery."""

from pathlib import Path
from unittest.mock import patch

import pytest

from run_apk.sdk import (
    AndroidTools,
    _resolve_executable,
    discover_tools,
    find_aapt2,
    find_adb,
    find_emulator,
    find_sdk_root,
    get_default_sdk_paths,
)


def test_get_default_sdk_paths_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    custom_home = tmp_path / "custom_home"
    monkeypatch.setenv("ANDROID_HOME", str(custom_home))
    paths = get_default_sdk_paths()
    assert custom_home in paths


def test_resolve_executable(tmp_path: Path):
    exe = tmp_path / "test_bin.exe"
    exe.write_text("dummy")

    with patch("sys.platform", "win32"):
        res = _resolve_executable(tmp_path, "test_bin")
        assert res == exe

    none_res = _resolve_executable(tmp_path / "nonexistent", "test_bin")
    assert none_res is None


def test_find_sdk_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sdk_dir = tmp_path / "AndroidSdk"
    (sdk_dir / "platform-tools").mkdir(parents=True)
    monkeypatch.setenv("ANDROID_HOME", str(sdk_dir))

    found = find_sdk_root()
    assert found == sdk_dir


def test_find_adb_in_sdk(tmp_path: Path):
    sdk_dir = tmp_path / "AndroidSdk"
    plat_tools = sdk_dir / "platform-tools"
    plat_tools.mkdir(parents=True)
    adb = plat_tools / "adb.exe"
    adb.write_text("binary")

    with patch("sys.platform", "win32"):
        found = find_adb(sdk_dir)
        assert found == adb


def test_find_emulator_in_sdk(tmp_path: Path):
    sdk_dir = tmp_path / "AndroidSdk"
    emu_dir = sdk_dir / "emulator"
    emu_dir.mkdir(parents=True)
    emulator = emu_dir / "emulator.exe"
    emulator.write_text("binary")

    with patch("sys.platform", "win32"):
        found = find_emulator(sdk_dir)
        assert found == emulator


def test_find_aapt2_in_sdk(tmp_path: Path):
    sdk_dir = tmp_path / "AndroidSdk"
    bt_dir = sdk_dir / "build-tools" / "34.0.0"
    bt_dir.mkdir(parents=True)
    aapt2 = bt_dir / "aapt2.exe"
    aapt2.write_text("binary")

    with patch("sys.platform", "win32"):
        found = find_aapt2(sdk_dir)
        assert found == aapt2


def test_discover_tools_success(tmp_path: Path):
    adb = tmp_path / "adb.exe"
    adb.write_text("binary")

    with (
        patch("run_apk.sdk.find_adb", return_value=adb),
        patch("run_apk.sdk.find_sdk_root", return_value=tmp_path),
        patch("run_apk.sdk.find_emulator", return_value=None),
        patch("run_apk.sdk.find_aapt2", return_value=None),
    ):
        tools = discover_tools()
        assert isinstance(tools, AndroidTools)
        assert tools.adb == adb
        assert tools.emulator is None
        assert tools.aapt2 is None


def test_discover_tools_missing_adb():
    with (
        patch("run_apk.sdk.find_adb", return_value=None),
        patch("run_apk.sdk.find_sdk_root", return_value=None),
    ):
        with pytest.raises(FileNotFoundError, match="Android Debug Bridge"):
            discover_tools()
