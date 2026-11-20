"""Command-line interface for run-apk."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from run_apk import __version__
from run_apk.apk import inspect_apk
from run_apk.device import resolve_device
from run_apk.runner import install_apk, launch_app, stream_logcat, take_screenshot
from run_apk.sdk import discover_tools

console = Console()
app = typer.Typer(
    name="run-apk",
    help="Fast, zero-config Android emulator runner and APK launcher CLI.",
    add_completion=False,
)


def version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold cyan]run-apk[/bold cyan] version [green]{__version__}[/green]")
        raise typer.Exit()


@app.command()
def run(
    apk_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the Android APK file to run.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    avd: Annotated[
        Optional[str],
        typer.Option("--avd", help="Name of the Android Virtual Device (AVD) to launch."),
    ] = None,
    device: Annotated[
        Optional[str],
        typer.Option("-d", "--device", help="Target specific ADB device serial."),
    ] = None,
    headless: Annotated[
        bool,
        typer.Option("--headless", help="Run the emulator in headless mode (-no-window)."),
    ] = False,
    no_launch: Annotated[
        bool,
        typer.Option("--no-launch", help="Install the APK without launching the main activity."),
    ] = False,
    wipe_data: Annotated[
        bool,
        typer.Option("--wipe-data", help="Wipe user data when booting the emulator (-wipe-data)."),
    ] = False,
    screenshot: Annotated[
        Optional[Path],
        typer.Option(
            "--screenshot",
            help="Capture a screenshot after launching and save to specified file.",
        ),
    ] = None,
    logcat: Annotated[
        bool,
        typer.Option("--logcat", help="Stream logcat output filtered to the app after launching."),
    ] = False,
    version: Annotated[
        Optional[bool],
        typer.Option(
            "-v",
            "--version",
            help="Show the version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """Run an APK file on an active Android device or automatically boot an emulator."""
    try:
        # Step 1: Discover Android SDK & tools
        tools = discover_tools()

        # Step 2: Inspect APK metadata
        with console.status("[bold cyan]Analyzing APK manifest...", spinner="dots"):
            apk_info = inspect_apk(apk_path, aapt2_path=tools.aapt2)

        # Print summary table
        table = Table(title="APK Metadata", show_header=True, header_style="bold magenta")
        table.add_column("Property", style="dim")
        table.add_column("Value", style="bold")
        table.add_row("File", apk_path.name)
        table.add_row("Package", apk_info.package_name)
        table.add_row("Version Name", apk_info.version_name or "N/A")
        table.add_row(
            "Version Code",
            str(apk_info.version_code) if apk_info.version_code is not None else "N/A",
        )
        table.add_row(
            "Main Activity",
            apk_info.main_activity or "[yellow]None (will use monkey fallback)[/yellow]",
        )
        console.print(table)

        # Step 3: Resolve target device (active device or boot emulator)
        target_serial = resolve_device(
            adb_path=tools.adb,
            emulator_path=tools.emulator,
            device_serial=device,
            avd_name=avd,
            headless=headless,
            wipe_data=wipe_data,
        )
        console.print(
            f"[bold green]Target Device Connected:[/bold green] [yellow]{target_serial}[/yellow]"
        )

        # Step 4: Install APK
        install_apk(adb_path=tools.adb, serial=target_serial, apk_path=apk_path)

        # Step 5: Launch app
        if not no_launch:
            launch_app(
                adb_path=tools.adb,
                serial=target_serial,
                package_name=apk_info.package_name,
                activity_name=apk_info.main_activity,
            )

        # Step 6: Optional Screenshot
        if screenshot is not None:
            # Short delay for UI render
            time.sleep(2)
            take_screenshot(adb_path=tools.adb, serial=target_serial, output_path=screenshot)

        # Step 7: Optional Logcat streaming
        if logcat:
            stream_logcat(
                adb_path=tools.adb,
                serial=target_serial,
                package_name=apk_info.package_name,
            )

    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        sys.exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
