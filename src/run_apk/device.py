"""Android device and emulator management utilities."""

from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

console = Console()


@dataclass(frozen=True)
class DeviceInfo:
    """Connected Android device details."""

    serial: str
    state: str
    is_emulator: bool


def list_devices(adb_path: Path) -> list[DeviceInfo]:
    """List all connected Android devices reported by adb."""
    try:
        proc = subprocess.run(
            [str(adb_path), "devices"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to query adb devices: {e}") from e

    devices: list[DeviceInfo] = []
    lines = proc.stdout.strip().splitlines()
    for line in lines[1:]:  # skip 'List of devices attached'
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"\s+", line)
        if len(parts) >= 2:
            serial = parts[0]
            state = parts[1]
            is_emulator = serial.startswith("emulator-")
            devices.append(DeviceInfo(serial=serial, state=state, is_emulator=is_emulator))

    return devices


def list_avds(emulator_path: Path | None) -> list[str]:
    """List available Android Virtual Devices (AVDs)."""
    if not emulator_path:
        return []

    try:
        proc = subprocess.run(
            [str(emulator_path), "-list-avds"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return [line.strip() for line in proc.stdout.strip().splitlines() if line.strip()]
    except Exception:
        return []


def boot_emulator(
    emulator_path: Path,
    avd_name: str,
    headless: bool = False,
    wipe_data: bool = False,
) -> subprocess.Popen:
    """Launch an Android emulator instance in the background."""
    cmd = [str(emulator_path), "-avd", avd_name]
    if headless:
        cmd.extend(["-no-window", "-no-audio"])
    if wipe_data:
        cmd.append("-wipe-data")

    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }

    if sys.platform == "win32":
        # Detached process on Windows so it keeps running independently
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    return subprocess.Popen(cmd, **kwargs)


def get_boot_status(adb_path: Path, serial: str) -> bool:
    """Check if the target device has finished booting."""
    try:
        proc = subprocess.run(
            [str(adb_path), "-s", serial, "shell", "getprop", "sys.boot_completed"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "1"
    except Exception:
        return False


def wait_for_boot(
    adb_path: Path,
    serial: str | None = None,
    timeout: float = 150.0,
    poll_interval: float = 2.0,
) -> str:
    """Poll until the target device or newly spawned emulator is fully booted."""
    start_time = time.time()
    target_serial = serial

    with console.status(
        "[bold green]Waiting for Android device / emulator to boot...", spinner="dots"
    ):
        while time.time() - start_time < timeout:
            # If target serial not set, find an attached device or emulator
            if not target_serial:
                devices = list_devices(adb_path)
                ready_devices = [d for d in devices if d.state == "device"]
                if ready_devices:
                    target_serial = ready_devices[0].serial

            if target_serial:
                if get_boot_status(adb_path, target_serial):
                    return target_serial

            time.sleep(poll_interval)

    raise TimeoutError(f"Android device failed to complete boot within {timeout} seconds.")


def resolve_device(
    adb_path: Path,
    emulator_path: Path | None,
    device_serial: str | None = None,
    avd_name: str | None = None,
    headless: bool = False,
    wipe_data: bool = False,
    timeout: float = 150.0,
) -> str:
    """Find an active device or start an emulator and wait for boot completion."""
    devices = list_devices(adb_path)

    # 1. User specified an explicit device serial
    if device_serial:
        matched = [d for d in devices if d.serial == device_serial]
        if not matched:
            raise RuntimeError(
                f"Specified device serial '{device_serial}' was not found in adb devices."
            )
        if matched[0].state != "device":
            # Still booting, wait for it
            return wait_for_boot(adb_path, serial=device_serial, timeout=timeout)
        return device_serial

    # 2. Check if there is already an online device running
    if not avd_name:
        ready_devices = [d for d in devices if d.state == "device"]
        if ready_devices:
            # Prefer physical devices or first running emulator
            return ready_devices[0].serial

    # 3. Need to boot an emulator
    if not emulator_path:
        raise RuntimeError(
            "No running Android devices found and 'emulator' binary could not be located."
        )

    available_avds = list_avds(emulator_path)
    if not available_avds:
        raise RuntimeError(
            "No connected Android devices found and no AVDs are configured.\n"
            "Create an AVD using Android Studio or 'avdmanager create avd'."
        )

    selected_avd = avd_name or available_avds[0]
    if selected_avd not in available_avds:
        raise RuntimeError(
            f"AVD '{selected_avd}' not found. Available AVDs: {', '.join(available_avds)}"
        )

    console.print(
        f"[bold cyan]Launching Android Emulator:[/bold cyan] {selected_avd} "
        f"(headless={headless}, wipe_data={wipe_data})"
    )
    boot_emulator(emulator_path, selected_avd, headless=headless, wipe_data=wipe_data)

    # Wait for device to boot and return serial
    return wait_for_boot(adb_path, timeout=timeout)
