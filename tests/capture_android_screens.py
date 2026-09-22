#!/usr/bin/env python3
"""Capture comparable screenshots from the Android emulator and phone.

The script deliberately uses only the Python standard library.  It retries
short-lived ADB server failures, prefers a numeric Tailscale serial when the
same phone is also visible through mDNS, and writes no device text or logs.

Example::

    python3 tests/capture_android_screens.py
    python3 tests/capture_android_screens.py --output /tmp/vaani-screens
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ADB_RETRIES = 5
ADB_RETRY_DELAY_SECONDS = 0.7
COMMAND_TIMEOUT_SECONDS = 20
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TAILSCALE_SERIAL = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}:\d+$")


@dataclass(frozen=True)
class Device:
    serial: str
    attributes: str
    role: str


def adb(args: list[str], *, binary: bool = False) -> bytes | str:
    """Run one ADB command, retrying transient daemon/socket failures."""
    command = ["adb", *args]
    last_error = "unknown ADB error"
    for attempt in range(ADB_RETRIES):
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=COMMAND_TIMEOUT_SECONDS,
                check=True,
            )
            return result.stdout if binary else result.stdout.decode("utf-8", "replace")
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            if isinstance(error, subprocess.CalledProcessError):
                detail = error.stderr.decode("utf-8", "replace").strip()
            else:
                detail = str(error)
            last_error = detail or type(error).__name__
            if attempt + 1 < ADB_RETRIES:
                time.sleep(ADB_RETRY_DELAY_SECONDS * (attempt + 1))
    raise RuntimeError(f"ADB command failed after {ADB_RETRIES} attempts: {' '.join(command)}\n{last_error}")


def connected_devices() -> list[Device]:
    listing = adb(["devices", "-l"])
    devices: list[Device] = []
    for line in listing.splitlines():
        fields = line.split()
        if len(fields) < 2 or fields[1] != "device":
            continue
        serial = fields[0]
        attributes = " ".join(fields[2:])
        emulator = serial.startswith("emulator-") or "model:sdk_" in attributes
        devices.append(Device(serial, attributes, "emulator" if emulator else "phone"))
    return devices


def choose_devices(devices: list[Device], emulator_serial: str | None, phone_serial: str | None) -> tuple[Device, Device]:
    emulators = [device for device in devices if device.role == "emulator"]
    phones = [device for device in devices if device.role == "phone"]
    if emulator_serial:
        emulators = [device for device in emulators if device.serial == emulator_serial]
    if phone_serial:
        phones = [device for device in phones if device.serial == phone_serial]

    if not emulators:
        raise RuntimeError("No connected emulator found. Check `adb devices -l`.")
    if not phones:
        raise RuntimeError("No connected phone found. Check the Tailscale ADB connection.")

    # A phone can appear twice (numeric Tailscale + adb-tls mDNS).  Prefer the
    # numeric serial because it is stable across mDNS discovery changes.
    phones.sort(key=lambda device: (not bool(TAILSCALE_SERIAL.match(device.serial)), device.serial))
    return emulators[0], phones[0]


def png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise RuntimeError("ADB returned data that is not a valid PNG screenshot")
    return struct.unpack(">II", data[16:24])


def capture(device: Device, output: Path) -> dict[str, object]:
    screenshot = adb(["-s", device.serial, "exec-out", "screencap", "-p"], binary=True)
    assert isinstance(screenshot, bytes)
    width, height = png_dimensions(screenshot)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(screenshot)
    return {
        "role": device.role,
        "serial": device.serial,
        "attributes": device.attributes,
        "file": str(output),
        "width": width,
        "height": height,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/tmp/vaani-screenshots"))
    parser.add_argument("--emulator-serial", help="Override automatic emulator selection")
    parser.add_argument("--phone-serial", help="Override automatic phone selection")
    args = parser.parse_args()

    try:
        emulator, phone = choose_devices(connected_devices(), args.emulator_serial, args.phone_serial)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        records = [
            capture(emulator, args.output / f"{timestamp}-emulator.png"),
            capture(phone, args.output / f"{timestamp}-phone.png"),
        ]
        metadata = {"captured_at": timestamp, "screenshots": records}
        metadata_path = args.output / f"{timestamp}-metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    except (RuntimeError, OSError) as error:
        print(f"capture_android_screens: {error}", file=sys.stderr)
        return 2

    for record in records:
        print(f"{record['role']}: {record['file']} ({record['width']}x{record['height']})")
    print(f"metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
