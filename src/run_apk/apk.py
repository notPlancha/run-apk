"""APK inspection and metadata extraction utilities."""

from __future__ import annotations

import re
import struct
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ApkInfo:
    """Parsed APK metadata."""

    package_name: str
    version_name: str | None = None
    version_code: int | None = None
    main_activity: str | None = None


class BinaryXmlParser:
    """Pure Python Android binary XML (AXML) parser."""

    RES_STRING_POOL_TYPE = 0x0001
    RES_XML_START_ELEMENT_TYPE = 0x0102
    RES_XML_END_ELEMENT_TYPE = 0x0103

    def __init__(self, data: bytes):
        self.data = data
        self.strings: list[str] = []

    def _read_u16(self, offset: int) -> int:
        return struct.unpack_from("<H", self.data, offset)[0]

    def _read_u32(self, offset: int) -> int:
        return struct.unpack_from("<I", self.data, offset)[0]

    def _parse_string_pool(self, offset: int) -> None:
        string_count = self._read_u32(offset + 8)
        flags = self._read_u32(offset + 16)
        strings_start = offset + self._read_u32(offset + 20)
        is_utf8 = bool(flags & (1 << 8))

        offsets: list[int] = []
        for i in range(string_count):
            offsets.append(self._read_u32(offset + 28 + (i * 4)))

        strings: list[str] = []
        for str_offset in offsets:
            pos = strings_start + str_offset
            if pos >= len(self.data):
                strings.append("")
                continue

            if is_utf8:
                char_len = self.data[pos]
                pos += 1
                if char_len & 0x80:
                    pos += 1

                if pos < len(self.data):
                    byte_len = self.data[pos]
                    pos += 1
                    if byte_len & 0x80:
                        byte_len = ((byte_len & 0x7F) << 8) | self.data[pos]
                        pos += 1
                    raw_str = self.data[pos : pos + byte_len]
                    strings.append(raw_str.decode("utf-8", errors="replace"))
                else:
                    strings.append("")
            else:
                char_len = self._read_u16(pos)
                pos += 2
                if char_len & 0x8000:
                    char_len = ((char_len & 0x7FFF) << 16) | self._read_u16(pos)
                    pos += 2
                raw_bytes = self.data[pos : pos + (char_len * 2)]
                strings.append(raw_bytes.decode("utf-16le", errors="replace"))

        self.strings = strings

    def parse_manifest(self) -> ApkInfo:
        """Parse AndroidManifest.xml binary data and extract package info."""
        if len(self.data) < 8:
            raise ValueError("Invalid binary XML: data too short")

        pos = 0
        total_len = len(self.data)

        # First chunk is usually RES_XML_TYPE (0x0003)
        chunk_type = self._read_u16(0)
        if chunk_type == 0x0003:
            pos = self._read_u16(2)

        package_name: str | None = None
        version_name: str | None = None
        version_code: int | None = None
        launchable_activity: str | None = None

        current_activity_name: str | None = None
        has_main_action = False
        has_launcher_category = False

        while pos + 8 <= total_len:
            c_type = self._read_u16(pos)
            c_size = self._read_u32(pos + 4)
            if c_size <= 0:
                break

            if c_type == self.RES_STRING_POOL_TYPE:
                self._parse_string_pool(pos)

            elif c_type == self.RES_XML_START_ELEMENT_TYPE:
                name_idx = self._read_u32(pos + 20)
                tag_name = self.strings[name_idx] if 0 <= name_idx < len(self.strings) else ""
                attr_start = self._read_u16(pos + 24)
                attr_size = self._read_u16(pos + 26)
                attr_count = self._read_u16(pos + 28)

                if tag_name in ("activity", "activity-alias"):
                    current_activity_name = None
                    has_main_action = False
                    has_launcher_category = False

                attrs: dict[str, tuple[str | None, int]] = {}
                attr_pos = pos + attr_start if attr_start >= 36 else pos + 16 + attr_start
                for _ in range(attr_count):
                    if attr_pos + 20 > total_len:
                        break
                    attr_name_idx = self._read_u32(attr_pos + 4)
                    attr_val_idx = self._read_u32(attr_pos + 8)
                    data_val = self._read_u32(attr_pos + 16)

                    a_name = (
                        self.strings[attr_name_idx]
                        if 0 <= attr_name_idx < len(self.strings)
                        else ""
                    )
                    a_str = (
                        self.strings[attr_val_idx]
                        if 0 <= attr_val_idx < len(self.strings)
                        else None
                    )
                    attrs[a_name] = (a_str, data_val)
                    attr_pos += attr_size

                if tag_name == "manifest":
                    if "package" in attrs:
                        package_name = attrs["package"][0]
                    if "versionName" in attrs:
                        version_name = attrs["versionName"][0]
                    if "versionCode" in attrs:
                        v_str, v_data = attrs["versionCode"]
                        if v_str and v_str.isdigit():
                            version_code = int(v_str)
                        else:
                            version_code = v_data

                elif tag_name in ("activity", "activity-alias"):
                    if "name" in attrs:
                        current_activity_name = attrs["name"][0]

                elif tag_name == "action":
                    if "name" in attrs:
                        action_name = attrs["name"][0]
                        if action_name == "android.intent.action.MAIN":
                            has_main_action = True

                elif tag_name == "category":
                    if "name" in attrs:
                        cat_name = attrs["name"][0]
                        if cat_name == "android.intent.category.LAUNCHER":
                            has_launcher_category = True

            elif c_type == self.RES_XML_END_ELEMENT_TYPE:
                name_idx = self._read_u32(pos + 20)
                tag_name = self.strings[name_idx] if 0 <= name_idx < len(self.strings) else ""
                if tag_name in ("activity", "activity-alias"):
                    if (
                        has_main_action
                        and has_launcher_category
                        and current_activity_name
                        and not launchable_activity
                    ):
                        launchable_activity = current_activity_name
                    current_activity_name = None
                    has_main_action = False
                    has_launcher_category = False

            pos += c_size

        if not package_name:
            raise ValueError("Could not find package name in AndroidManifest.xml")

        # Resolve relative activity names (e.g. ".MainActivity" -> "com.example.MainActivity")
        if launchable_activity:
            if launchable_activity.startswith("."):
                launchable_activity = f"{package_name}{launchable_activity}"
            elif "." not in launchable_activity:
                launchable_activity = f"{package_name}.{launchable_activity}"

        return ApkInfo(
            package_name=package_name,
            version_name=version_name,
            version_code=version_code,
            main_activity=launchable_activity,
        )


def _inspect_apk_pure_python(apk_path: Path) -> ApkInfo:
    """Inspect APK by reading binary AndroidManifest.xml directly from zip archive."""
    with zipfile.ZipFile(apk_path, "r") as zf:
        manifest_data = zf.read("AndroidManifest.xml")

    parser = BinaryXmlParser(manifest_data)
    return parser.parse_manifest()


def _inspect_apk_aapt2(apk_path: Path, aapt2_path: Path) -> ApkInfo | None:
    """Inspect APK using aapt2 dump badging."""
    try:
        proc = subprocess.run(
            [str(aapt2_path), "dump", "badging", str(apk_path)],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        output = proc.stdout

        package_match = re.search(r"package:\s+name='([^']+)'", output)
        if not package_match:
            return None
        package_name = package_match.group(1)

        version_code_match = re.search(r"versionCode='([^']*)'", output)
        version_code = (
            int(version_code_match.group(1))
            if version_code_match and version_code_match.group(1).isdigit()
            else None
        )

        version_name_match = re.search(r"versionName='([^']*)'", output)
        version_name = version_name_match.group(1) if version_name_match else None

        activity_match = re.search(r"launchable-activity:\s+name='([^']+)'", output)
        main_activity = activity_match.group(1) if activity_match else None

        return ApkInfo(
            package_name=package_name,
            version_name=version_name,
            version_code=version_code,
            main_activity=main_activity,
        )
    except Exception:
        return None


def inspect_apk(apk_path: str | Path, aapt2_path: Path | None = None) -> ApkInfo:
    """Inspect an APK file and extract package name, version, and launchable activity."""
    path = Path(apk_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"APK file not found: {path}")

    # Try aapt2 first if available
    if aapt2_path:
        info = _inspect_apk_aapt2(path, aapt2_path)
        if info:
            return info

    # Fallback to pure Python binary XML parser
    return _inspect_apk_pure_python(path)
