"""
Windows PnPUtil helpers for Explorer Advance — PnPUtil.

Lists third-party driver packages from the driver store via `pnputil`.
CSV output is preferred (language-independent headers). Text listing is
parsed as a fallback for older Windows builds. A follow-up pass adds
`/files` and `/ids` when the Windows build supports them. `/enum-devices
/problem` lists Device Manager problem codes.
"""

from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

INF_DIR = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "INF"
DRIVER_STORE = (
    Path(os.environ.get("SystemRoot", r"C:\Windows"))
    / "System32"
    / "DriverStore"
    / "FileRepository"
)


# ---------------------------------------------------------------------------
# Process helpers
# ---------------------------------------------------------------------------


def is_windows() -> bool:
    return sys.platform == "win32"


def creationflags_no_window() -> int:
    if is_windows():
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return 0


@dataclass(slots=True)
class PnpRun:
    args: list[str]
    returncode: int
    text: str
    timed_out: bool = False

    @property
    def command(self) -> str:
        return format_command(self.args)

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def format_command(args: list[str]) -> str:
    parts: list[str] = ["pnputil"]
    for item in args:
        if any(ch.isspace() for ch in item) or not item:
            parts.append('"' + item.replace('"', "") + '"')
        else:
            parts.append(item)
    return " ".join(parts)


def _decode(raw: bytes) -> str:
    if not raw:
        return ""
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    for enc in ("utf-8-sig", "utf-16-le", "cp65001", "cp1252", "cp850", "oem", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def run_pnputil(args: list[str], *, timeout: float = 180) -> PnpRun:
    """Run pnputil.exe and return exit code plus combined text."""
    try:
        completed = subprocess.run(
            ["pnputil", *args],
            capture_output=True,
            timeout=timeout,
            creationflags=creationflags_no_window(),
        )
    except FileNotFoundError:
        return PnpRun(args=list(args), returncode=127, text="pnputil.exe was not found.")
    except subprocess.TimeoutExpired as exc:
        raw = (exc.stdout or b"") + (exc.stderr or b"")
        text = _decode(raw).strip()
        if not text:
            text = f"pnputil timed out after {timeout:.0f} seconds."
        return PnpRun(args=list(args), returncode=124, text=text, timed_out=True)

    raw = completed.stdout or b""
    if completed.stderr:
        raw = raw + (b"\n" if raw else b"") + completed.stderr
    return PnpRun(
        args=list(args),
        returncode=int(completed.returncode),
        text=_decode(raw).strip(),
    )


# ---------------------------------------------------------------------------
# Driver package model
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DriverDevice:
    instance_id: str
    description: str
    status: str = ""
    problem_code: str = ""
    problem_status: str = ""

    @property
    def has_problem(self) -> bool:
        code = (self.problem_code or "").strip()
        return bool(code) and code not in {"0", "0x0", "0x00000000"}


@dataclass(slots=True)
class DriverPackage:
    published: str
    original: str
    provider: str
    class_name: str
    class_guid: str = ""
    class_version: str = ""
    extension_id: str = ""
    driver_date: str = ""
    driver_date_ts: float = 0.0
    version: str = ""
    signer: str = ""
    catalog: str = ""
    whcp: str = ""
    catalog_file: str = ""
    files: list[str] = field(default_factory=list)
    package_id: str = ""
    family_id: str = ""
    devices: list[DriverDevice] = field(default_factory=list)
    duplicate: str = ""  # "" | "latest" | "older"
    sibling_count: int = 1

    @property
    def in_use(self) -> bool:
        return bool(self.devices)

    @property
    def inf_path(self) -> str:
        if not self.published:
            return ""
        return str(INF_DIR / self.published)

    @property
    def store_path(self) -> str:
        if not self.package_id:
            return ""
        return str(DRIVER_STORE / self.package_id)

    @property
    def has_problem(self) -> bool:
        return any(dev.has_problem for dev in self.devices)

    def to_row(self) -> dict:
        devices = self.devices
        names = [d.description for d in devices if d.description]
        problems = sum(1 for d in devices if d.has_problem)
        return {
            "published": self.published,
            "original": self.original,
            "provider": self.provider,
            "class_name": self.class_name,
            "class_guid": self.class_guid,
            "date": self.driver_date,
            "date_ts": self.driver_date_ts,
            "version": self.version,
            "signer": self.signer,
            "catalog": self.catalog,
            "whcp": self.whcp,
            "catalog_file": self.catalog_file,
            "package_id": self.package_id,
            "family_id": self.family_id,
            "file_count": len(self.files),
            "in_use": "Yes" if devices else "No",
            "device_count": len(devices),
            "device_summary": ", ".join(names[:2])
            + (f" +{len(names) - 2}" if len(names) > 2 else ""),
            "has_problem": problems > 0,
            "duplicate": self.duplicate,
            "sibling_count": self.sibling_count,
            "inf_path": self.inf_path,
            "store_path": self.store_path,
            "search": " ".join(
                [
                    self.published,
                    self.original,
                    self.provider,
                    self.class_name,
                    self.version,
                    self.signer,
                    self.catalog,
                    self.catalog_file,
                    self.package_id,
                    self.family_id,
                    *self.files,
                    *names,
                ]
            ).lower(),
        }


@dataclass(slots=True)
class DriverInventory:
    packages: list[DriverPackage]
    command: str
    raw: str = ""
    format_used: str = "csv"
    error: str = ""
    extra_commands: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass(slots=True)
class ProblemDevice:
    instance_id: str
    description: str
    class_name: str = ""
    manufacturer: str = ""
    status: str = ""
    problem_code: str = ""
    problem_status: str = ""
    driver_name: str = ""
    extension_drivers: str = ""

    @property
    def meaning(self) -> str:
        return problem_meaning(self.problem_code)


@dataclass(slots=True)
class ProblemInventory:
    devices: list[ProblemDevice]
    command: str
    raw: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


# SetupAPI / Device Manager problem codes (CM_PROB_*).
_PROBLEM_MEANINGS: dict[int, str] = {
    1: "Not configured",
    3: "Driver is corrupted or failed",
    10: "Failed to start",
    12: "Not enough resources",
    14: "Need to restart the computer",
    16: "Unknown resources",
    18: "Drivers need to be reinstalled",
    19: "Registry is incomplete or damaged",
    21: "Removing",
    22: "Disabled",
    24: "Not present or not working",
    28: "Drivers not installed",
    29: "Disabled by firmware",
    31: "Device is not working properly",
    32: "Driver service is disabled",
    33: "Translator failed",
    34: "Needs a reinstall / config",
    35: "Firmware is missing",
    37: "Driver returned a failure",
    39: "Driver is missing or corrupt",
    41: "Failed after a reboot",
    43: "Stopped because of a driver failure",
    44: "Closed (surprise removal)",
    45: "Not connected",
    47: "Halting pending replacement",
    48: "Driver blocked from loading",
    52: "Unsigned driver",
    54: "Used by another device",
}


def _parse_problem_int(code: str) -> Optional[int]:
    text = (code or "").strip().lower()
    if not text:
        return None
    try:
        if text.startswith("0x"):
            return int(text, 16)
        return int(text, 10)
    except ValueError:
        return None


def problem_meaning(code: str) -> str:
    number = _parse_problem_int(code)
    if number is None:
        return ""
    return _PROBLEM_MEANINGS.get(number, "")


# ---------------------------------------------------------------------------
# Date / version parsing
# ---------------------------------------------------------------------------


def parse_driver_version_field(value: str) -> tuple[str, str, float]:
    """
    Split a PnPUtil DriverVersion cell into (iso_date, version, timestamp).

    Typical value: ``08/21/2025 25.30.0.1`` (US date + version).
    """
    text = (value or "").strip().strip('"')
    if not text:
        return "", "", 0.0

    date_part = ""
    version_part = text
    bits = text.split(None, 1)
    if bits and _looks_like_date(bits[0]):
        date_part = bits[0]
        version_part = bits[1].strip() if len(bits) > 1 else ""

    iso, ts = _parse_date(date_part)
    return iso, version_part, ts


def _looks_like_date(token: str) -> bool:
    return bool(
        token
        and (
            token.count("/") == 2
            or token.count("-") == 2
            or token.count(".") == 2
        )
        and any(ch.isdigit() for ch in token)
    )


def _parse_date(value: str) -> tuple[str, float]:
    text = (value or "").strip()
    if not text:
        return "", 0.0
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%Y-%m-%d"), dt.timestamp()
        except ValueError:
            continue
    return text, 0.0


# ---------------------------------------------------------------------------
# CSV + text parsers
# ---------------------------------------------------------------------------


_TEXT_KEY_MAP = {
    "published name": "published",
    "nom publié": "published",
    "nom publie": "published",
    "original name": "original",
    "nom d'origine": "original",
    "nom dorigine": "original",
    "provider name": "provider",
    "nom du fournisseur": "provider",
    "class name": "class_name",
    "nom de la classe": "class_name",
    "class guid": "class_guid",
    "guid de la classe": "class_guid",
    "class version": "class_version",
    "extension id": "extension_id",
    "driver version": "driver_version",
    "version du pilote": "driver_version",
    "signer name": "signer",
    "nom du signataire": "signer",
    "catalog attributes": "catalog",
    "whcp version": "whcp",
}


def _norm_key(key: str) -> str:
    return (
        key.strip()
        .lower()
        .replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
        .replace("’", "'")
    )


def _cell(row: dict[str, str], *names: str) -> str:
    for name in names:
        if name in row and row[name] is not None:
            return str(row[name]).strip().strip('"')
    lower = {k.lower(): v for k, v in row.items()}
    for name in names:
        value = lower.get(name.lower())
        if value is not None:
            return str(value).strip().strip('"')
    return ""


def _package_from_fields(fields: dict[str, str]) -> DriverPackage:
    date_iso, version, ts = parse_driver_version_field(fields.get("driver_version", ""))
    return DriverPackage(
        published=fields.get("published", ""),
        original=fields.get("original", ""),
        provider=fields.get("provider", ""),
        class_name=fields.get("class_name", ""),
        class_guid=fields.get("class_guid", ""),
        class_version=fields.get("class_version", ""),
        extension_id=fields.get("extension_id", ""),
        driver_date=date_iso,
        driver_date_ts=ts,
        version=version,
        signer=fields.get("signer", ""),
        catalog=fields.get("catalog", ""),
        whcp=fields.get("whcp", ""),
    )


def _csv_rows(text: str, *header_markers: str) -> list[dict[str, str]]:
    """Parse a pnputil CSV listing, skipping the banner before the header."""
    sample = (text or "").lstrip()
    if not sample:
        return []
    lines = sample.splitlines()
    start = 0
    markers = tuple(marker.lower() for marker in header_markers)
    for i, line in enumerate(lines):
        low = line.lower()
        if any(marker in low for marker in markers):
            start = i
            break
    blob = "\n".join(lines[start:])
    reader = csv.DictReader(io.StringIO(blob))
    if not reader.fieldnames:
        return []
    return [row for row in reader if row]


def parse_enum_drivers_csv(text: str) -> list[DriverPackage]:
    """Parse `/enum-drivers [/devices] /format csv` into packages."""
    reader_rows = _csv_rows(text, "DriverName", "Published Name", "PublishedName")
    if not reader_rows:
        return []

    by_name: dict[str, DriverPackage] = {}
    order: list[str] = []

    for raw in reader_rows:
        published = _cell(raw, "DriverName", "PublishedName", "Published Name")
        if not published:
            continue
        original = _cell(raw, "OriginalName", "Original Name")
        device_id = _cell(raw, "Device")
        description = _cell(raw, "DeviceDescription", "Device Description")

        if published not in by_name:
            pkg = _package_from_fields(
                {
                    "published": published,
                    "original": original,
                    "provider": _cell(raw, "ProviderName", "Provider Name"),
                    "class_name": _cell(raw, "ClassName", "Class Name"),
                    "class_guid": _cell(raw, "ClassGuid", "Class GUID"),
                    "class_version": _cell(raw, "ClassVersion", "Class Version"),
                    "extension_id": _cell(raw, "ExtensionId", "Extension ID"),
                    "driver_version": _cell(raw, "DriverVersion", "Driver Version"),
                    "signer": _cell(raw, "SignerName", "Signer Name"),
                    "catalog": _cell(raw, "CatalogAttributes", "Catalog Attributes"),
                    "whcp": _cell(raw, "WhcpVersion", "WHCP Version"),
                }
            )
            by_name[published] = pkg
            order.append(published)
        elif original and not by_name[published].original:
            by_name[published].original = original

        if device_id or description:
            by_name[published].devices.append(
                DriverDevice(
                    instance_id=device_id,
                    description=description,
                    status=_cell(raw, "Status", "DeviceStatus", "Device Status"),
                    problem_code=_cell(raw, "ProblemCode", "Problem Code"),
                    problem_status=_cell(raw, "ProblemStatus", "Problem Status"),
                )
            )

    return [by_name[name] for name in order]


def parse_enum_drivers_text(text: str) -> list[DriverPackage]:
    """Parse the default localized `/enum-drivers` listing."""
    packages: list[DriverPackage] = []
    current: dict[str, str] = {}

    def flush() -> None:
        if current.get("published"):
            packages.append(_package_from_fields(current))
        current.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        mapped = _TEXT_KEY_MAP.get(_norm_key(key))
        if mapped:
            current[mapped] = value.strip()
    flush()
    return packages


def attach_files_csv(packages: list[DriverPackage], text: str) -> None:
    """Attach `/enum-drivers /files` catalog + file names onto packages."""
    by_name = {pkg.published: pkg for pkg in packages}
    for raw in _csv_rows(text, "DriverName"):
        published = _cell(raw, "DriverName", "PublishedName", "Published Name")
        pkg = by_name.get(published)
        if pkg is None:
            continue
        catalog = _cell(raw, "CatalogFile", "Catalog File")
        filename = _cell(raw, "File")
        if catalog and not pkg.catalog_file:
            pkg.catalog_file = catalog
        if filename and filename not in pkg.files:
            pkg.files.append(filename)


def attach_ids_csv(packages: list[DriverPackage], text: str) -> None:
    """Attach `/enum-drivers /ids` package and family IDs onto packages."""
    by_name = {pkg.published: pkg for pkg in packages}
    for raw in _csv_rows(text, "DriverName"):
        published = _cell(raw, "DriverName", "PublishedName", "Published Name")
        pkg = by_name.get(published)
        if pkg is None:
            continue
        package_id = _cell(raw, "DriverPackageId", "Driver Package Id")
        family_id = _cell(raw, "FamilyId", "Family Id")
        if package_id and not pkg.package_id:
            pkg.package_id = package_id
        if family_id and not pkg.family_id:
            pkg.family_id = family_id


def _looks_like_instance_id(value: str) -> bool:
    text = (value or "").strip()
    if not text or " " in text:
        return False
    return "\\" in text or text.startswith("{")


def parse_enum_devices_csv(text: str) -> list[ProblemDevice]:
    """Parse `/enum-devices … /format csv` into device rows (problem list)."""
    devices: list[ProblemDevice] = []
    seen: set[str] = set()
    for raw in _csv_rows(text, "InstanceId", "Instance ID"):
        instance_id = _cell(raw, "InstanceId", "Instance ID")
        if not _looks_like_instance_id(instance_id) or instance_id in seen:
            continue
        seen.add(instance_id)
        devices.append(
            ProblemDevice(
                instance_id=instance_id,
                description=_cell(raw, "DeviceDescription", "Device Description"),
                class_name=_cell(raw, "ClassName", "Class Name"),
                manufacturer=_cell(raw, "ManufacturerName", "Manufacturer Name"),
                status=_cell(raw, "Status"),
                problem_code=_cell(raw, "ProblemCode", "Problem Code"),
                problem_status=_cell(raw, "ProblemStatus", "Problem Status"),
                driver_name=_cell(raw, "DriverName", "Driver Name"),
                extension_drivers=_cell(
                    raw, "ExtensionDriverNames", "Extension Driver Names"
                ),
            )
        )
    return devices


def _enrich_packages(packages: list[DriverPackage]) -> list[str]:
    """Best-effort `/files` and `/ids` pass. Ignored on older Windows builds."""
    commands: list[str] = []
    files_run = run_pnputil(["/enum-drivers", "/files", "/format", "csv"])
    if files_run.returncode != 127 and "DriverName" in files_run.text:
        attach_files_csv(packages, files_run.text)
        commands.append(files_run.command)
    ids_run = run_pnputil(["/enum-drivers", "/ids", "/format", "csv"], timeout=60)
    if ids_run.returncode != 127 and "DriverName" in ids_run.text:
        attach_ids_csv(packages, ids_run.text)
        commands.append(ids_run.command)
    return commands


def mark_duplicates(packages: list[DriverPackage]) -> None:
    """Tag older packages that share the same original INF name."""
    groups: dict[str, list[DriverPackage]] = {}
    for pkg in packages:
        key = (pkg.original or "").casefold()
        if not key:
            continue
        groups.setdefault(key, []).append(pkg)

    for group in groups.values():
        if len(group) < 2:
            continue
        ranked = sorted(
            group,
            key=lambda p: (p.driver_date_ts, p.version),
            reverse=True,
        )
        for index, pkg in enumerate(ranked):
            pkg.sibling_count = len(ranked)
            pkg.duplicate = "latest" if index == 0 else "older"


def siblings_of(
    packages: list[DriverPackage], *, original: str
) -> list[DriverPackage]:
    """Packages that share `original` INF name, newest date/version first."""
    key = (original or "").strip().casefold()
    if not key:
        return []
    group = [pkg for pkg in packages if (pkg.original or "").casefold() == key]
    return sorted(
        group,
        key=lambda pkg: (pkg.driver_date_ts, pkg.version),
        reverse=True,
    )


# ---------------------------------------------------------------------------
# Public inventory API
# ---------------------------------------------------------------------------


def enum_drivers() -> DriverInventory:
    """
    List third-party OEM driver packages.

    Tries CSV + devices first, then CSV, then the classic text listing.
    """
    attempts = [
        (["/enum-drivers", "/devices", "/format", "csv"], "csv+devices"),
        (["/enum-drivers", "/format", "csv"], "csv"),
        (["/enum-drivers"], "text"),
    ]
    last = PnpRun(args=["/enum-drivers"], returncode=1, text="")
    last_label = "text"

    for args, label in attempts:
        last = run_pnputil(args)
        last_label = label
        if last.returncode == 127:
            return DriverInventory(
                packages=[],
                command=last.command,
                raw=last.text,
                format_used=label,
                error=last.text,
            )
        if not last.ok:
            continue
        if "csv" in label:
            packages = parse_enum_drivers_csv(last.text)
        else:
            packages = parse_enum_drivers_text(last.text)
        if packages:
            mark_duplicates(packages)
            extras = _enrich_packages(packages)
            return DriverInventory(
                packages=packages,
                command=last.command,
                raw=last.text,
                format_used=label,
                extra_commands=extras,
            )

    error = last.text or "pnputil returned no driver packages."
    if last.returncode not in (0, 127) and last.text:
        error = f"pnputil exited with code {last.returncode}.\n{last.text}"
    return DriverInventory(
        packages=[],
        command=last.command,
        raw=last.text,
        format_used=last_label,
        error=error,
    )


def load_inspect() -> tuple[DriverInventory, ProblemInventory]:
    """OEM packages (with files/ids) plus devices that report a problem."""
    return enum_drivers(), enum_problem_devices()


def format_problem_code(code: str) -> str:
    text = (code or "").strip() or "—"
    meaning = problem_meaning(code)
    if meaning and text != "—":
        return f"{text} — {meaning}"
    return text


def enum_problem_devices() -> ProblemInventory:
    """List devices that currently report a Device Manager problem code."""
    args = ["/enum-devices", "/problem", "/format", "csv"]
    result = run_pnputil(args, timeout=60)
    if result.returncode == 127:
        return ProblemInventory(
            devices=[], command=result.command, raw=result.text, error=result.text
        )
    if "InstanceId" in result.text or "Instance ID" in result.text:
        return ProblemInventory(
            devices=parse_enum_devices_csv(result.text),
            command=result.command,
            raw=result.text,
        )
    if result.ok:
        return ProblemInventory(
            devices=[], command=result.command, raw=result.text
        )
    error = result.text or "pnputil /enum-devices /problem failed."
    return ProblemInventory(
        devices=[], command=result.command, raw=result.text, error=error
    )


def classes_from(packages: list[DriverPackage]) -> list[str]:
    names = sorted({p.class_name for p in packages if p.class_name}, key=str.casefold)
    return names


def providers_from(packages: list[DriverPackage]) -> list[str]:
    names = sorted({p.provider for p in packages if p.provider}, key=str.casefold)
    return names


def sort_packages(
    packages: list[DriverPackage],
    *,
    key: str = "date_desc",
) -> list[DriverPackage]:
    items = list(packages)
    if key == "date_asc":
        items.sort(key=lambda p: (p.driver_date_ts or 0.0, p.published.casefold()))
    elif key == "provider":
        items.sort(key=lambda p: (p.provider.casefold(), p.original.casefold()))
    elif key == "class":
        items.sort(key=lambda p: (p.class_name.casefold(), p.provider.casefold()))
    elif key == "published":
        items.sort(key=lambda p: _oem_sort_key(p.published))
    elif key == "original":
        items.sort(key=lambda p: (p.original.casefold(), p.driver_date_ts or 0.0))
    else:  # date_desc
        items.sort(
            key=lambda p: (p.driver_date_ts or 0.0, p.published.casefold()),
            reverse=True,
        )
    return items


def _oem_sort_key(name: str) -> tuple[int, str]:
    stem = name.lower().removesuffix(".inf").removeprefix("oem")
    if stem.isdigit():
        return (int(stem), name.casefold())
    return (10**9, name.casefold())


def filter_packages(
    packages: list[DriverPackage],
    *,
    query: str = "",
    class_name: str = "",
    provider: str = "",
    in_use_only: bool = False,
    older_only: bool = False,
    problems_only: bool = False,
) -> list[DriverPackage]:
    q = (query or "").strip().lower()
    out: list[DriverPackage] = []
    for pkg in packages:
        if class_name and pkg.class_name != class_name:
            continue
        if provider and pkg.provider != provider:
            continue
        if in_use_only and not pkg.in_use:
            continue
        if older_only and pkg.duplicate != "older":
            continue
        if problems_only and not pkg.has_problem:
            continue
        if q:
            hay = " ".join(
                [
                    pkg.published,
                    pkg.original,
                    pkg.provider,
                    pkg.class_name,
                    pkg.version,
                    pkg.signer,
                    pkg.catalog,
                    pkg.catalog_file,
                    pkg.package_id,
                    pkg.family_id,
                    *pkg.files,
                    *(d.description for d in pkg.devices),
                    *(d.instance_id for d in pkg.devices),
                ]
            ).lower()
            if q not in hay:
                continue
        out.append(pkg)
    return out


# ---------------------------------------------------------------------------
# Explorer / export
# ---------------------------------------------------------------------------


def pick_folder(start: str = "") -> Optional[str]:
    """Native Windows folder dialog (tkinter). Returns None if cancelled."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        initial = start if start and Path(start).is_dir() else str(Path.home())
        path = filedialog.askdirectory(initialdir=initial, title="Select export folder")
        root.destroy()
        return path or None
    except Exception:
        return None


def open_in_explorer(path: str) -> None:
    """Reveal `path` in Explorer. Folders open; files are selected."""
    target = Path(path)
    if not target.exists():
        parent = target.parent
        if parent.exists():
            os.startfile(parent)
        else:
            raise FileNotFoundError(path)
        return
    if target.is_dir():
        os.startfile(target)
        return
    subprocess.Popen(["explorer", "/n", f"/select,{target}"])


def export_drivers(published_names: list[str], dest: str) -> PnpRun:
    """Export one or more OEM packages (or ``*``) into `dest`."""
    Path(dest).mkdir(parents=True, exist_ok=True)
    names = [n for n in published_names if n]
    if not names:
        return PnpRun(args=[], returncode=1, text="No driver package selected.")
    if len(names) == 1:
        return run_pnputil(["/export-driver", names[0], dest], timeout=300)
    # Export each package so a single failure is visible per name.
    chunks: list[str] = []
    code = 0
    timed_out = False
    for name in names:
        result = run_pnputil(["/export-driver", name, dest], timeout=300)
        chunks.append(f"$ {result.command}\n{result.text or '(no output)'}")
        if not result.ok:
            code = result.returncode or 1
            timed_out = timed_out or result.timed_out
    return PnpRun(
        args=["/export-driver", "<selection>", dest],
        returncode=code,
        text="\n\n".join(chunks),
        timed_out=timed_out,
    )


def driver_help() -> str:
    result = run_pnputil(["/?"], timeout=20)
    return result.text
