# run-apk

Fast, zero-config Android emulator runner and APK launcher CLI.

`run-apk` inspects your APK, discovers your Android SDK installation, finds an active device or automatically boots an Android Virtual Device (AVD), installs the APK, and launches the main activity.

---

## Key Highlights

- **Instant Zero-Config Execution**: Simply provide `run-apk path/to/app.apk`.
- **Pure Python APK Parser**: Reads package name, version, and launchable main activity directly from `AndroidManifest.xml` binary XML in the APK without requiring external binaries (with optional `aapt2` acceleration when available).
- **Automatic Emulator Lifecycle**: Detects active hardware devices and running emulators; boots your configured AVD if no device is online, waiting cleanly for complete boot.
- **Headless & Cold Start Support**: Run emulators without windows in CI/headless environments (`--headless`) and cold start wiping user data (`--wipe-data`).
- **Developer Utilities**: Built-in screenshot capture (`--screenshot output.png`) and application logcat streaming (`--logcat`).

---

## Installation

### With uv (Recommended)

```bash
uv tool install git+https://github.com/notPlancha/run-apk.git
```

### With pipx

```bash
pipx install git+https://github.com/notPlancha/run-apk.git
```

### Local Development

```bash
git clone https://github.com/notPlancha/run-apk.git
cd run-apk
uv sync
uv run pytest
```

---

## Usage Examples

### 1. Basic Run

Launches the APK on the first online device or boots the default AVD:

```bash
run-apk build/outputs/apk/debug/app-debug.apk
```

### 2. Boot Specific AVD Headless

```bash
run-apk app.apk --avd Pixel_7_API_34 --headless
```

### 3. Install and Capture Screenshot

```bash
run-apk app.apk --screenshot preview.png
```

### 4. Cold Boot and Stream Logs

```bash
run-apk app.apk --wipe-data --logcat
```

---

## Command Options

| Option | Flag | Description |
| :--- | :--- | :--- |
| `apk_path` | Position 1 | Path to Android APK file to run (required) |
| `--avd` | | Specify Android Virtual Device (AVD) name |
| `--device` | `-d` | Direct execution to specific ADB serial |
| `--headless` | | Boot emulator in headless mode (`-no-window`) |
| `--no-launch` | | Install APK without starting main activity |
| `--wipe-data` | | Wipe user data on emulator boot (`-wipe-data`) |
| `--screenshot` | | Path to save captured device screenshot |
| `--logcat` | | Stream filtered device logs to terminal |
| `--version` | `-v` | Display `run-apk` version and exit |
| `--help` | | Show usage help and options |

---

## Architecture

- `run_apk.sdk`: Discovers Android SDK roots, `adb`, `emulator`, and `aapt2` across Windows, macOS, and Linux.
- `run_apk.apk`: Dual-engine APK analyzer featuring an in-memory binary XML chunk parser and fallback to `aapt2 dump badging`.
- `run_apk.device`: Manages attached devices, enumerates AVDs, boots background emulators, and polls `sys.boot_completed`.
- `run_apk.runner`: Handles APK package installation, activity launching with monkey intent fallback, screencap retrieval, and logcat streaming.
- `run_apk.cli`: Typer interface with Rich terminal visual styling.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
