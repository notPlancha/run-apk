"""APK installation, execution, screenshot, and logcat utilities."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console

console = Console()


def install_apk(adb_path: Path, serial: str, apk_path: Path) -> None:
    """Install APK onto the target Android device."""
    console.print(
        f"[bold cyan]Installing APK:[/bold cyan] {apk_path.name} on [yellow]{serial}[/yellow]..."
    )
    cmd = [str(adb_path), "-s", serial, "install", "-r", "-d", str(apk_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip()
        # If downgrade or signature conflict, try reinstalling with uninstall first if needed
        raise RuntimeError(f"Failed to install APK: {err}")

    if "Success" not in proc.stdout:
        console.print(f"[yellow]Warning:[/yellow] Unexpected install output: {proc.stdout.strip()}")
    else:
        console.print("[bold green]✓ APK installed successfully.[/bold green]")


def launch_app(
    adb_path: Path,
    serial: str,
    package_name: str,
    activity_name: str | None = None,
) -> None:
    """Launch the application's main activity or trigger default launcher intent."""
    if activity_name:
        component = f"{package_name}/{activity_name}"
        console.print(f"[bold cyan]Starting Activity:[/bold cyan] [green]{component}[/green]")
        cmd = [
            str(adb_path),
            "-s",
            serial,
            "shell",
            "am",
            "start",
            "-n",
            component,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or "Error:" in proc.stdout or "Error:" in proc.stderr:
            err = proc.stderr.strip() or proc.stdout.strip()
            console.print(
                f"[yellow]Launch failed ({err}), falling back to monkey launcher...[/yellow]"
            )
            _launch_via_monkey(adb_path, serial, package_name)
        else:
            console.print("[bold green]✓ App launched successfully.[/bold green]")
    else:
        console.print(
            f"[bold cyan]No main activity declared. Launching via monkey:[/bold cyan] "
            f"[green]{package_name}[/green]"
        )
        _launch_via_monkey(adb_path, serial, package_name)


def _launch_via_monkey(adb_path: Path, serial: str, package_name: str) -> None:
    """Fallback launch mechanism using Android's monkey utility."""
    cmd = [
        str(adb_path),
        "-s",
        serial,
        "shell",
        "monkey",
        "-p",
        package_name,
        "-c",
        "android.intent.category.LAUNCHER",
        "1",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(f"Failed to launch app with monkey: {err}")
    console.print("[bold green]✓ App launched via monkey intent.[/bold green]")


def take_screenshot(adb_path: Path, serial: str, output_path: Path) -> Path:
    """Capture a screenshot from the target device and save to local disk."""
    resolved_path = output_path.resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    remote_tmp = "/sdcard/run_apk_screenshot.png"
    # Take screenshot on device
    subprocess.run(
        [str(adb_path), "-s", serial, "shell", "screencap", "-p", remote_tmp],
        check=True,
        capture_output=True,
    )

    # Pull file to local machine
    subprocess.run(
        [str(adb_path), "-s", serial, "pull", remote_tmp, str(resolved_path)],
        check=True,
        capture_output=True,
    )

    # Clean up device temp file
    subprocess.run(
        [str(adb_path), "-s", serial, "shell", "rm", "-f", remote_tmp],
        capture_output=True,
    )

    console.print(
        f"[bold green]✓ Screenshot saved to:[/bold green] [yellow]{resolved_path}[/yellow]"
    )
    return resolved_path


def stream_logcat(
    adb_path: Path,
    serial: str,
    package_name: str | None = None,
) -> None:
    """Stream logcat output to console, optionally filtered by package PID."""
    console.print(
        f"[bold cyan]Streaming logcat for [yellow]{serial}[/yellow]... (Ctrl+C to stop)[/bold cyan]"
    )

    cmd = [str(adb_path), "-s", serial, "logcat", "-v", "time"]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        target_pid: str | None = None
        if package_name:
            # Query PID for package
            try:
                pid_proc = subprocess.run(
                    [str(adb_path), "-s", serial, "shell", "pidof", "-s", package_name],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if pid_proc.returncode == 0 and pid_proc.stdout.strip():
                    target_pid = pid_proc.stdout.strip()
            except Exception:
                pass

        if proc.stdout:
            for line in proc.stdout:
                line_str = line.rstrip()
                if not line_str:
                    continue
                if package_name and target_pid:
                    if target_pid in line_str or package_name in line_str:
                        console.print(line_str)
                elif package_name:
                    if package_name in line_str:
                        console.print(line_str)
                else:
                    console.print(line_str)

    except KeyboardInterrupt:
        console.print("\n[yellow]Logcat stream stopped.[/yellow]")
    finally:
        if "proc" in locals() and proc.poll() is None:
            proc.terminate()
