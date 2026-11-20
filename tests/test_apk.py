"""Tests for APK inspection and binary XML parsing."""

import struct
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from run_apk.apk import (
    BinaryXmlParser,
    _inspect_apk_aapt2,
    inspect_apk,
)


def create_minimal_binary_manifest(
    package: str = "com.example.test",
    version_name: str = "1.0.0",
    version_code: int = 10,
    activity_name: str = "MainActivity",
    has_launcher: bool = True,
) -> bytes:
    """Helper to synthesize valid binary AndroidManifest.xml bytes."""
    strings = [
        "manifest",
        "package",
        package,
        "versionName",
        version_name,
        "versionCode",
        "activity",
        "name",
        activity_name,
        "action",
        "android.intent.action.MAIN",
        "category",
        "android.intent.category.LAUNCHER",
    ]

    encoded = []
    offsets = []
    curr_off = 0
    for s in strings:
        offsets.append(curr_off)
        data = s.encode("utf-16le")
        item = struct.pack("<H", len(s)) + data + b"\x00\x00"
        encoded.append(item)
        curr_off += len(item)

    str_data = b"".join(encoded)
    pool_header_size = 28
    pool_chunk_size = pool_header_size + len(offsets) * 4 + len(str_data)
    pad = (4 - (pool_chunk_size % 4)) % 4
    str_data += b"\x00" * pad
    pool_chunk_size += pad

    pool = (
        struct.pack(
            "<HHIIIIII",
            0x0001,
            28,
            pool_chunk_size,
            len(strings),
            0,
            0,
            28 + len(offsets) * 4,
            0,
        )
        + struct.pack(f"<{len(offsets)}I", *offsets)
        + str_data
    )

    # manifest element
    manifest_attrs = (
        struct.pack("<IIIHBB I", 0xFFFFFFFF, 1, 2, 8, 0, 3, 2)
        + struct.pack("<IIIHBB I", 0xFFFFFFFF, 3, 4, 8, 0, 3, 4)
        + struct.pack("<IIIHBB I", 0xFFFFFFFF, 5, 0xFFFFFFFF, 8, 0, 16, version_code)
    )
    manifest_elem = (
        struct.pack(
            "<HHIIIIIHHHHHH",
            0x0102,
            16,
            36 + len(manifest_attrs),
            1,
            0xFFFFFFFF,
            0xFFFFFFFF,
            0,
            20,
            20,
            3,
            0,
            0,
            0,
        )
        + manifest_attrs
    )

    # activity element
    act_attrs = struct.pack("<IIIHBB I", 0xFFFFFFFF, 7, 8, 8, 0, 3, 8)
    act_elem = (
        struct.pack(
            "<HHIIIIIHHHHHH",
            0x0102,
            16,
            36 + len(act_attrs),
            2,
            0xFFFFFFFF,
            0xFFFFFFFF,
            6,
            20,
            20,
            1,
            0,
            0,
            0,
        )
        + act_attrs
    )

    body_parts = [pool, manifest_elem, act_elem]

    if has_launcher:
        action_attrs = struct.pack("<IIIHBB I", 0xFFFFFFFF, 7, 10, 8, 0, 3, 10)
        action_elem = (
            struct.pack(
                "<HHIIIIIHHHHHH",
                0x0102,
                16,
                36 + len(action_attrs),
                3,
                0xFFFFFFFF,
                0xFFFFFFFF,
                9,
                20,
                20,
                1,
                0,
                0,
                0,
            )
            + action_attrs
        )

        cat_attrs = struct.pack("<IIIHBB I", 0xFFFFFFFF, 7, 12, 8, 0, 3, 12)
        cat_elem = (
            struct.pack(
                "<HHIIIIIHHHHHH",
                0x0102,
                16,
                36 + len(cat_attrs),
                4,
                0xFFFFFFFF,
                0xFFFFFFFF,
                11,
                20,
                20,
                1,
                0,
                0,
                0,
            )
            + cat_attrs
        )

        body_parts.extend([action_elem, cat_elem])

    end_act = struct.pack("<HHIIIII", 0x0103, 16, 24, 5, 0xFFFFFFFF, 0xFFFFFFFF, 6)
    end_manifest = struct.pack("<HHIIIII", 0x0103, 16, 24, 6, 0xFFFFFFFF, 0xFFFFFFFF, 0)
    body_parts.extend([end_act, end_manifest])

    body = b"".join(body_parts)
    header = struct.pack("<HHI", 0x0003, 8, 8 + len(body))
    return header + body


def test_binary_xml_parser():
    data = create_minimal_binary_manifest(
        package="org.example.demo",
        version_name="2.1.0",
        version_code=42,
        activity_name=".MainActivity",
        has_launcher=True,
    )
    parser = BinaryXmlParser(data)
    info = parser.parse_manifest()

    assert info.package_name == "org.example.demo"
    assert info.version_name == "2.1.0"
    assert info.version_code == 42
    assert info.main_activity == "org.example.demo.MainActivity"


def test_binary_xml_no_launcher():
    data = create_minimal_binary_manifest(
        package="org.example.service",
        has_launcher=False,
    )
    parser = BinaryXmlParser(data)
    info = parser.parse_manifest()

    assert info.package_name == "org.example.service"
    assert info.main_activity is None


def test_inspect_apk_pure_python(tmp_path: Path):
    apk_file = tmp_path / "test.apk"
    manifest_bytes = create_minimal_binary_manifest(
        package="com.myapp",
        version_name="3.0",
        version_code=300,
        activity_name="HomeActivity",
    )

    with zipfile.ZipFile(apk_file, "w") as zf:
        zf.writestr("AndroidManifest.xml", manifest_bytes)

    info = inspect_apk(apk_file)
    assert info.package_name == "com.myapp"
    assert info.version_name == "3.0"
    assert info.version_code == 300
    assert info.main_activity == "com.myapp.HomeActivity"


def test_inspect_apk_aapt2(tmp_path: Path):
    apk_file = tmp_path / "test.apk"
    apk_file.write_text("fake apk")

    mock_output = (
        "package: name='com.aapt.app' versionCode='99' versionName='9.9.0' compileSdkVersion='34'\n"
        "sdkVersion:'21'\n"
        "application-label:'AAPT App'\n"
        "launchable-activity: name='com.aapt.app.SplashActivity'  label='Splash' icon=''\n"
    )

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(return_value=0, stdout=mock_output, returncode=0)
        info = _inspect_apk_aapt2(apk_file, Path("aapt2"))

        assert info is not None
        assert info.package_name == "com.aapt.app"
        assert info.version_code == 99
        assert info.version_name == "9.9.0"
        assert info.main_activity == "com.aapt.app.SplashActivity"


def test_inspect_apk_not_found():
    with pytest.raises(FileNotFoundError):
        inspect_apk("non_existent_file.apk")
