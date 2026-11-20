"""Android SDK and tool discovery utilities."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AndroidTools:
    """Collection of detected Android SDK tool paths."""

    sdk_root: Path | None
    adb: Path
    emulator: Path | None = None
    aapt2: Path | None = None


def get_default_sdk_paths() -> list[Path]:
    """Return platform-specific candidate locations for the Android SDK."""
    candidates: list[Path] = []

    # Environment variables have highest precedence
    for env_var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        val = os.environ.get(env_var)
        if val:
            candidates.append(Path(val).expanduser().resolve())

    # Platform-specific standard default locations
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "Android" / "Sdk")
        candidates.append(Path.home() / "AppData" / "Local" / "Android" / "Sdk")
    elif sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "Android" / "sdk")
    else:
        # Linux and other Unixes
        candidates.append(Path.home() / "Android" / "Sdk")
        candidates.append(Path("/usr/lib/android-sdk"))

    return candidates


def _resolve_executable(base_dir: Path | None, binary_name: str) -> Path | None:
    """Find executable in base_dir with or without .exe extension."""
    if base_dir is None or not base_dir.is_dir():
        return None

    names = [binary_name, f"{binary_name}.exe"] if sys.platform == "win32" else [binary_name]
    for name in names:
        candidate = base_dir / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        if candidate.is_file() and sys.platform == "win32":
            return candidate

    return None


def _find_in_path(binary_name: str) -> Path | None:
    """Find binary in system PATH."""
    found = shutil.which(binary_name)
    return Path(found).resolve() if found else None


def find_sdk_root() -> Path | None:
    """Locate the root directory of the Android SDK if present on disk."""
    for candidate in get_default_sdk_paths():
        if candidate.is_dir():
            # Basic validation: check for platform-tools or platforms
            if (candidate / "platform-tools").is_dir() or (candidate / "emulator").is_dir():
                return candidate

    # Infer from adb in PATH if possible
    adb_path = _find_in_path("adb")
    if adb_path:
        # e.g. <sdk>/platform-tools/adb -> <sdk>
        parent = adb_path.parent
        if parent.name == "platform-tools" and parent.parent.is_dir():
            return parent.parent

    return None


def find_adb(sdk_root: Path | None = None) -> Path | None:
    """Locate the adb executable."""
    if sdk_root:
        adb = _resolve_executable(sdk_root / "platform-tools", "adb")
        if adb:
            return adb

    return _find_in_path("adb")


def find_emulator(sdk_root: Path | None = None) -> Path | None:
    """Locate the emulator executable."""
    if sdk_root:
        emulator = _resolve_executable(sdk_root / "emulator", "emulator")
        if emulator:
            return emulator

    return _find_in_path("emulator")


def find_aapt2(sdk_root: Path | None = None) -> Path | None:
    """Locate the aapt2 executable in build-tools or PATH."""
    if sdk_root:
        build_tools_dir = sdk_root / "build-tools"
        if build_tools_dir.is_dir():
            # Pick latest version directory
            versions = sorted(
                [d for d in build_tools_dir.iterdir() if d.is_dir()],
                key=lambda d: d.name,
                reverse=True,
            )
            for version_dir in versions:
                aapt2 = _resolve_executable(version_dir, "aapt2")
                if aapt2:
                    return aapt2

    return _find_in_path("aapt2")


def discover_tools() -> AndroidTools:
    """Discover all available Android tools, raising an error if adb is missing."""
    sdk_root = find_sdk_root()
    adb = find_adb(sdk_root)

    if not adb:
        raise FileNotFoundError(
            "Android Debug Bridge ('adb') could not be found. "
            "Please ensure Android SDK or platform-tools are installed and added to PATH "
            "or set the ANDROID_HOME environment variable."
        )

    emulator = find_emulator(sdk_root)
    aapt2 = find_aapt2(sdk_root)

    return AndroidTools(
        sdk_root=sdk_root,
        adb=adb,
        emulator=emulator,
        aapt2=aapt2,
    )
