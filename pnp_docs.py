"""
Reference text for the PnPUtil manual and command-map tabs.

Commands match `pnputil /?` on current Windows (including
`/enum-devicetree`, `/enum-containers`, `/format`, and `/force`),
plus the official Microsoft docs.
"""

from __future__ import annotations

from typing import TypedDict


class PnpCommand(TypedDict):
    id: str
    switch: str
    title: str
    syntax: str
    group: str
    status: str  # ready | inspect | planned
    danger: bool
    summary: str
    details: str
    examples: list[str]


GROUPS = [
    "Inspect",
    "Driver store",
    "Devices",
    "Help",
]


BEGINNER_SECTIONS: list[tuple[str, str]] = [
    (
        "A device needs a driver package",
        "Hardware (a GPU, a sound chip, a network card, a USB gadget) talks to "
        "Windows through a **driver**. A **driver package** is the recipe plus "
        "the files: an **INF** (what to install, which hardware IDs it matches) "
        "and the binaries (`.sys`, a catalog `.cat`, sometimes firmware or an "
        "app). When you plug a device in, or run a vendor installer, Windows "
        "**Setup** copies that package into a private cache — the **driver "
        "store** — then binds a matching package to the live device. Device "
        "Manager is the GUI for that. `pnputil` is the scriptable one.",
    ),
    (
        "Two kinds of drivers",
        "**In-box** drivers ship with Windows (Microsoft). **OEM** (third-party) "
        "drivers come from the vendor, Windows Update, or an installer you ran. "
        "`pnputil /enum-drivers` lists **OEM packages only**. That is what the "
        "**Installed drivers** tab shows. A PC can have a modest set of devices "
        "and still dozens of OEM packages.",
    ),
    (
        "Why they are called oem0.inf, oem17.inf, …",
        "When Setup accepts a third-party package, it **publishes** a copy of "
        "the INF under `C:\\Windows\\INF` with a generated name: `oem0.inf`, "
        "`oem17.inf`, `oem38.inf`. **OEM** here means third-party, not “the PC "
        "maker” in particular. The number is only an index — it is not a "
        "version and it does not mean “better”. The vendor’s original name "
        "(for example `rtkvhd64.inf`) stays on the package as **Original "
        "name**. The real files live in the driver store "
        "(`FileRepository\\…`), not only in that published INF.",
    ),
    (
        "Why you see “Latest of 3”",
        "Windows does **not** throw away an old package when a newer one "
        "arrives. Several copies of the same original INF can sit side by "
        "side — last year’s Realtek audio next to this year’s. Each copy has "
        "its own `oem#.inf`. This app ranks those copies by **driver date**, "
        "then version. **Latest of 3** means this row is the newest of three "
        "packages that share that original INF. Live devices usually bind to "
        "the latest. The older copies stay until someone deletes them. Click "
        "the badge on **Installed drivers** to see the family.",
    ),
]


OVERVIEW_WHAT_MD = """
**`pnputil.exe`** (Microsoft PnP Utility) is the built-in Windows command that
manages the **driver store** and, on recent Windows 10/11 builds, **devices**
themselves. It lives in `%windir%\\system32` from Windows Vista onward.

- The **driver store** is Windows’ private cache of third-party packages
  (`C:\\Windows\\System32\\DriverStore\\FileRepository`).
- Packages that Setup copied there are published as **`oem#.inf`**
  (oem0.inf, oem17.inf, …) under `C:\\Windows\\INF`.
- **`/enum-drivers` lists those OEM packages only** — not the in-box
  Microsoft drivers that ship with Windows.
- Device Manager is the GUI cousin. `pnputil` is the scriptable one.
"""

OVERVIEW_STORE_MD = """
When you install a vendor driver, Windows copies the INF and its files into
the store, then *publishes* a copy as `oem#.inf`. Several versions of the same
original INF can sit side by side (an older Realtek audio next to a newer
one). The newest ranked package is what a live device usually uses; the older
copies stay until you delete them. That is why a PC can show dozens of OEM
packages even with a modest set of devices.
"""

GOLDEN_RULES: list[tuple[str, str]] = [
    (
        "Listing is always safe.",
        "`/enum-drivers`, `/enum-devices`, and the other `/enum-*` commands only read.",
    ),
    (
        "Delete without /uninstall leaves a hole.",
        "Removes the package from the store but can leave devices pointing at a missing INF. Prefer `/delete-driver oem#.inf /uninstall` when you mean “take this off the PC”.",
    ),
    (
        "/force is the sharp edge.",
        "On delete, disable, or remove it will do it even if a device is using the package or the device is “critical”. Do not use `/force` unless you can recover (safe mode, another display, a boot USB).",
    ),
    (
        "Elevation changes who you are.",
        "Many write commands need an elevated Command Prompt (Run as administrator). A listing from a normal prompt is enough for this app’s inventory tab.",
    ),
]


QUICKSTART_STEPS: list[dict[str, object]] = [
    {
        "title": "List every third-party driver package",
        "commands": ["pnputil /enum-drivers"],
        "note": (
            "Each block is one OEM package: published name (`oem17.inf`), "
            "original INF, provider, class, **date + version**, and signer. "
            "The **Installed drivers** tab runs the same command (CSV form) "
            "so you can search and sort."
        ),
    },
    {
        "title": "See which devices use those packages",
        "commands": ["pnputil /enum-drivers /devices"],
        "note": (
            "On current Windows this appends the live devices bound to each "
            "package."
        ),
    },
    {
        "title": "Export a package (backup before you delete)",
        "commands": [
            r"pnputil /export-driver oem17.inf D:\DriverBackup",
            r"pnputil /export-driver * D:\DriverBackup",
        ],
        "note": "`*` exports the whole OEM store. Harmless: it only copies files out.",
    },
    {
        "title": "Add a driver from a folder (and install it)",
        "commands": [
            r"pnputil /add-driver D:\Drivers\net.inf /install",
            r"pnputil /add-driver D:\Drivers\*.inf /subdirs /install",
        ],
        "note": (
            "`/install` updates matching devices. Without it, the package "
            "only enters the store and waits."
        ),
    },
    {
        "title": "Remove an old package",
        "commands": ["pnputil /delete-driver oem4.inf /uninstall"],
        "note": (
            "Add `/force` only if Windows says the package is still in use "
            "and you are sure nothing needs it."
        ),
    },
    {
        "title": "Find devices that are not happy",
        "commands": [
            "pnputil /enum-devices /problem",
            "pnputil /enum-devices /connected /drivers",
        ],
        "note": (
            "`/problem` is the command-line version of the yellow triangle "
            "in Device Manager."
        ),
    },
    {
        "title": "Rescan hardware",
        "commands": ["pnputil /scan-devices"],
        "note": "Same idea as “Scan for hardware changes” in Device Manager.",
    },
]


SAFE_COMMANDS: list[tuple[str, str]] = [
    ("pnputil /enum-drivers", "Read-only list of OEM packages"),
    ("pnputil /enum-devices", "Read-only list of devices"),
    ("pnputil /enum-classes", "Read-only setup classes"),
    ("pnputil /enum-interfaces", "Read-only device interfaces"),
    ("pnputil /enum-devicetree", "Read-only tree"),
    ("pnputil /enum-containers", "Read-only device containers"),
    ("pnputil /export-driver", "Copies files out of the store"),
    ("pnputil /?", "Help text"),
]

INTENT_COMMANDS: list[tuple[str, str]] = [
    ("/add-driver", "Adds a package to the store"),
    ("/add-driver /install", "Also updates matching devices"),
    ("/delete-driver", "Removes a package from the store"),
    ("/enable-device  /  /disable-device", "Power state of a device"),
    ("/restart-device", "Cycles a device"),
    ("/scan-devices", "Triggers a Plug and Play rescan"),
]

DANGER_POINTS: list[tuple[str, str]] = [
    (
        "/delete-driver oem#.inf /force",
        "Removes the package even if a live device is bound to it. Display, storage, and chipset drivers are the usual way to get a black screen or a missing disk.",
    ),
    (
        "/disable-device  /  /remove-device with /force",
        "Can disable or yank a device Windows marked as critical (keyboard, boot disk, GPU).",
    ),
    (
        "/remove-device /subtree",
        "Deletes the device and its children.",
    ),
    (
        "/reboot",
        "Will restart the PC if the operation says it is required.",
    ),
]


COMPARE_ITEMS: list[tuple[str, str]] = [
    (
        "Device Manager",
        "The GUI. `pnputil` is the same Plug and Play stack, scriptable.",
    ),
    (
        "`driverquery`",
        "Lists *running* drivers / services, not the OEM store. Complementary, not a replacement.",
    ),
    (
        "Windows Update / Optional updates",
        "Another source of packages; once installed they still show up as `oem#.inf`.",
    ),
    (
        "DISM `/Add-Driver`",
        "Offline image servicing (a WIM / VHD). `pnputil` talks to the *running* OS.",
    ),
    (
        "`devcon.exe`",
        "The older WDK tool. Most of what people used `devcon` for is now in `pnputil`.",
    ),
]


ROADMAP_MD = """
This version ships three working surfaces:

1. **Installed drivers** — run `pnputil /enum-drivers`, search and sort the
   OEM store (date, provider, class), see which devices use a package, list
   files (`/files`) and store IDs (`/ids`) in Details, show Device Manager
   problem devices (`/enum-devices /problem`), and export a selection.
2. **PnPUtil manual** + **Command map** — the full switch list, with
   examples.

Later tabs can wrap the remaining write commands (add, delete, enable,
disable) as guided actions. The map below is the backlog.
"""


COMMANDS: list[PnpCommand] = [
    {
        "id": "enum_drivers",
        "switch": "/enum-drivers",
        "title": "List third-party driver packages",
        "syntax": (
            "pnputil /enum-drivers [/class <name | GUID>] [/files] [/ids] "
            "[/devices] [/format <txt | xml | csv>] [/output-file [filename]]"
        ),
        "group": "Inspect",
        "status": "ready",
        "danger": False,
        "summary": "Enumerate every OEM package in the driver store.",
        "details": (
            "This is the inventory this app is built around. Without extra "
            "flags it prints one block per `oem#.inf`. `/class` keeps a single "
            "setup class (Display, Net, MEDIA, …). `/files` lists every file "
            "inside the package — the Details dialog shows that list. `/ids` "
            "adds the driver-store package ID and family ID (the "
            "FileRepository folder name). `/devices` shows which live devices "
            "currently use it. `/format csv` is what the Installed drivers tab "
            "parses (headers stay in English even on a French Windows). "
            "Available since Windows 10 1607; `/class` from Windows 11 21H2, "
            "`/files` and `/ids` from 22H2."
        ),
        "examples": [
            "pnputil /enum-drivers",
            'pnputil /enum-drivers /class "Display"',
            "pnputil /enum-drivers /devices /format csv",
            "pnputil /enum-drivers /files",
            "pnputil /enum-drivers /ids /format csv",
        ],
    },
    {
        "id": "enum_devices",
        "switch": "/enum-devices",
        "title": "List devices on the system",
        "syntax": (
            "pnputil /enum-devices [/connected | /disconnected] "
            "[/class <name | GUID>] [/instanceid <id> | /deviceid <id>] "
            "[/problem [code]] [/bus [name | GUID]] [/deviceids] [/relations] "
            "[/services] [/stack] [/location] [/drivers] [/interfaces] "
            "[/properties] [/resources] [/format <txt | xml | csv>]"
        ),
        "group": "Inspect",
        "status": "inspect",
        "danger": False,
        "summary": "Enumerate devices — connected, disconnected, or with problems.",
        "details": (
            "The command-line Device Manager. `/connected` and `/disconnected` "
            "split present vs ghost devices. `/problem` is every device with a "
            "problem code (yellow triangle); `/problem 28` (or `0x1C`) filters "
            "one code. The Installed drivers tab runs `/enum-devices /problem` "
            "and shows the list (including in-box drivers) plus a filter for "
            "OEM packages bound to a problem device. `/drivers` shows the "
            "matching and installed packages. The reverse view "
            "(`/enum-drivers /devices`) is already on each package. A full "
            "device browser can come later. Available since Windows 10 1903; "
            "many extra flags arrived in 2004 and Windows 11."
        ),
        "examples": [
            "pnputil /enum-devices /connected",
            "pnputil /enum-devices /problem",
            "pnputil /enum-devices /class Display /drivers",
            r'pnputil /enum-devices /instanceid "ACPI\PNP0A08\1"',
        ],
    },
    {
        "id": "enum_devicetree",
        "switch": "/enum-devicetree",
        "title": "Show the device tree",
        "syntax": (
            "pnputil /enum-devicetree [root instance ID] [/connected] "
            "[/services] [/stack] [/drivers] [/interfaces]"
        ),
        "group": "Inspect",
        "status": "planned",
        "danger": False,
        "summary": "Walk Plug and Play from a root device down through children.",
        "details": (
            "Prints the same parent/child tree Device Manager shows in View → "
            "Devices by connection. Pass a root instance ID to start lower "
            "(for example a PCI root). Windows 11 23H2+."
        ),
        "examples": [
            "pnputil /enum-devicetree",
            r'pnputil /enum-devicetree "ACPI\PNP0A03\0"',
            "pnputil /enum-devicetree /connected /drivers",
        ],
    },
    {
        "id": "enum_classes",
        "switch": "/enum-classes",
        "title": "List device setup classes",
        "syntax": (
            "pnputil /enum-classes [/class <name | GUID>] [/services] "
            "[/format <txt | xml | csv>]"
        ),
        "group": "Inspect",
        "status": "planned",
        "danger": False,
        "summary": "Enumerate setup classes (Display, Net, System, MEDIA, …).",
        "details": (
            "Useful when you want the official class name or GUID before "
            "filtering `/enum-drivers /class` or `/enum-devices /class`. "
            "Windows 11 22H2+."
        ),
        "examples": [
            "pnputil /enum-classes",
            "pnputil /enum-classes /class Display",
            "pnputil /enum-classes /class {4d36e968-e325-11ce-bfc1-08002be10318}",
        ],
    },
    {
        "id": "enum_interfaces",
        "switch": "/enum-interfaces",
        "title": "List device interfaces",
        "syntax": (
            "pnputil /enum-interfaces [/enabled | /disabled] [/class <GUID>] "
            "[/instanceid <id>] [/properties] [/format <txt | xml | csv>]"
        ),
        "group": "Inspect",
        "status": "planned",
        "danger": False,
        "summary": "Enumerate device interface paths (the symbolic links apps open).",
        "details": (
            "Interfaces are not the devices themselves — they are the published "
            "paths (GUID + reference string) that user-mode software uses. "
            "Filter with `/enabled`, `/disabled`, or an interface class GUID. "
            "Windows 10 1903+."
        ),
        "examples": [
            "pnputil /enum-interfaces /enabled",
            "pnputil /enum-interfaces /class {884b96c3-56ef-11d1-bc8c-00a0c91405dd}",
        ],
    },
    {
        "id": "enum_containers",
        "switch": "/enum-containers",
        "title": "List device containers",
        "syntax": (
            "pnputil /enum-containers [/containerid <id>] "
            "[/connected | /disconnected] [/problem] [/devices] "
            "[/format <txt | xml | csv>]"
        ),
        "group": "Inspect",
        "status": "planned",
        "danger": False,
        "summary": "Enumerate physical device containers (one gadget, many functions).",
        "details": (
            "A container is the physical object — a USB headset, a laptop, a "
            "monitor — that may expose several device nodes. `/devices` lists "
            "the nodes inside each container. Windows 11 23H2+."
        ),
        "examples": [
            "pnputil /enum-containers",
            "pnputil /enum-containers /connected /devices",
            'pnputil /enum-containers /containerid "{00000000-0000-0000-ffff-ffffffffffff}"',
        ],
    },
    {
        "id": "add_driver",
        "switch": "/add-driver",
        "title": "Add a driver package to the store",
        "syntax": (
            "pnputil /add-driver <filename.inf | *.inf> [/subdirs] "
            "[/install] [/reboot]"
        ),
        "group": "Driver store",
        "status": "planned",
        "danger": False,
        "summary": "Copy one or many INF packages into the driver store.",
        "details": (
            "Without `/install` the package is staged only. With `/install` "
            "Windows also updates any existing device that this package ranks "
            "for. `/subdirs` walks a tree of vendor folders (the usual "
            "`D:\\Drivers\\*.inf /subdirs /install` pattern). If the new "
            "package is not the highest-ranked match, PnPUtil will not force "
            "it onto the device. Needs elevation. Windows 10 1607+."
        ),
        "examples": [
            r"pnputil /add-driver x:\driver.inf",
            r"pnputil /add-driver c:\oem\*.inf",
            r"pnputil /add-driver D:\Drivers\*.inf /subdirs /install",
        ],
    },
    {
        "id": "delete_driver",
        "switch": "/delete-driver",
        "title": "Delete a driver package from the store",
        "syntax": "pnputil /delete-driver <oem#.inf> [/uninstall] [/force] [/reboot]",
        "group": "Driver store",
        "status": "planned",
        "danger": True,
        "summary": "Remove an OEM package. Prefer /uninstall; /force is the sharp edge.",
        "details": (
            "`/uninstall` detaches the package from devices that use it before "
            "deleting the store copy. Without it, you only delete the store "
            "entry. `/force` deletes even when a device is still bound — that "
            "is how display or storage drivers disappear from under Windows. "
            "Export first. Needs elevation. The Installed drivers tab shows "
            "the published name you must pass (`oem17.inf`)."
        ),
        "examples": [
            "pnputil /delete-driver oem0.inf",
            "pnputil /delete-driver oem4.inf /uninstall",
            "pnputil /delete-driver oem1.inf /uninstall /force",
        ],
    },
    {
        "id": "export_driver",
        "switch": "/export-driver",
        "title": "Export driver packages to a folder",
        "syntax": "pnputil /export-driver <oem#.inf | *> <target directory>",
        "group": "Driver store",
        "status": "ready",
        "danger": False,
        "summary": "Copy one package, or every OEM package, out of the store.",
        "details": (
            "Read-only from the system’s point of view: files are copied to "
            "the folder you name. `*` is the whole OEM store — useful before "
            "a clean install or before deleting old copies. Wired to "
            "**Export** on the Installed drivers tab. May need elevation on "
            "some systems."
        ),
        "examples": [
            r"pnputil /export-driver oem6.inf .",
            r"pnputil /export-driver oem17.inf D:\DriverBackup",
            r"pnputil /export-driver * D:\DriverBackup",
        ],
    },
    {
        "id": "disable_device",
        "switch": "/disable-device",
        "title": "Disable devices",
        "syntax": (
            "pnputil /disable-device [<instance ID> | /deviceid <device ID>] "
            "[/class <name | GUID>] [/bus <name | GUID>] [/reboot] [/force]"
        ),
        "group": "Devices",
        "status": "planned",
        "danger": True,
        "summary": "Disable one device, or every device matching an ID / class / bus.",
        "details": (
            "Same as Device Manager → Disable. Pass a full instance ID, or "
            "use `/deviceid` for every device with that hardware/compatible "
            "ID. `/force` disables even critical devices. Windows 10 2004+; "
            "filters grew in Windows 11."
        ),
        "examples": [
            r'pnputil /disable-device "USB\VID_045E&PID_00DB\6&870CE29&0&1"',
            r'pnputil /disable-device /deviceid "USB\Class_03"',
            r'pnputil /disable-device /class "USB" /bus "PCI"',
        ],
    },
    {
        "id": "enable_device",
        "switch": "/enable-device",
        "title": "Enable devices",
        "syntax": (
            "pnputil /enable-device [<instance ID> | /deviceid <device ID>] "
            "[/class <name | GUID>] [/bus <name | GUID>] [/reboot]"
        ),
        "group": "Devices",
        "status": "planned",
        "danger": False,
        "summary": "Enable a previously disabled device (or a matching set).",
        "details": (
            "Mirror of `/disable-device`. Same filters. Windows 10 2004+."
        ),
        "examples": [
            r'pnputil /enable-device "USB\VID_045E&PID_00DB\6&870CE29&0&1"',
            r'pnputil /enable-device /deviceid "USB\Class_03"',
        ],
    },
    {
        "id": "restart_device",
        "switch": "/restart-device",
        "title": "Restart devices",
        "syntax": (
            "pnputil /restart-device [<instance ID> | /deviceid <device ID>] "
            "[/class <name | GUID>] [/bus <name | GUID>] [/reboot]"
        ),
        "group": "Devices",
        "status": "planned",
        "danger": False,
        "summary": "Cycle a device — disable then enable in one step.",
        "details": (
            "Useful after a driver update when a device is stuck. Same "
            "instance / device-id / class / bus filters as enable/disable. "
            "Windows 10 2004+."
        ),
        "examples": [
            r'pnputil /restart-device "USB\VID_045E&PID_00DB\6&870CE29&0&1"',
            r'pnputil /restart-device /class "Net"',
        ],
    },
    {
        "id": "remove_device",
        "switch": "/remove-device",
        "title": "Remove devices from the system",
        "syntax": (
            "pnputil /remove-device [<instance ID> | /deviceid <device ID>] "
            "[/class <name | GUID>] [/bus <name | GUID>] [/subtree] "
            "[/reboot] [/force]"
        ),
        "group": "Devices",
        "status": "planned",
        "danger": True,
        "summary": "Unplug a device node in software. /subtree also removes children.",
        "details": (
            "Same idea as Device Manager → Uninstall device (without the "
            "“delete driver” checkbox — that is `/delete-driver`). `/subtree` "
            "removes the node and every child. `/force` ignores the critical-"
            "device guard. A later `/scan-devices` often brings present "
            "hardware back. Windows 10 2004+."
        ),
        "examples": [
            r'pnputil /remove-device "USB\VID_045E&PID_00DB\6&870CE29&0&1"',
            r'pnputil /remove-device /deviceid "USB\Class_03"',
        ],
    },
    {
        "id": "scan_devices",
        "switch": "/scan-devices",
        "title": "Scan for hardware changes",
        "syntax": "pnputil /scan-devices [/instanceid <instance ID>] [/async]",
        "group": "Devices",
        "status": "planned",
        "danger": False,
        "summary": "Ask Plug and Play to look again — Device Manager’s hardware scan.",
        "details": (
            "Without flags, scans the whole machine. `/instanceid` limits the "
            "walk to one subtree. `/async` returns before the scan finishes. "
            "Windows 10 2004+."
        ),
        "examples": [
            "pnputil /scan-devices",
            r'pnputil /scan-devices /instanceid "PCI\VEN_8086&DEV_A36D\3&11583659&0&14"',
        ],
    },
    {
        "id": "help",
        "switch": "/?",
        "title": "Show usage",
        "syntax": "pnputil /?",
        "group": "Help",
        "status": "ready",
        "danger": False,
        "summary": "Print the built-in help. Localized to the Windows UI language.",
        "details": (
            "Switches stay in English (`/enum-drivers`, `/force`, …) even when "
            "the descriptions are in French (or another language). The Command "
            "map in this app is the English field guide; `/ ?` is the copy "
            "that shipped with this PC."
        ),
        "examples": ["pnputil /?"],
    },
    {
        "id": "legacy",
        "switch": "-e / -a / -d",
        "title": "Legacy short switches",
        "syntax": "pnputil -e    |    pnputil -a [-i] file.inf    |    pnputil -d [-f] oem#.inf",
        "group": "Help",
        "status": "inspect",
        "danger": False,
        "summary": "Old Vista-era flags. Still work; prefer the /enum-drivers style.",
        "details": (
            "`-e` is `/enum-drivers`. `-a` is `/add-driver` (`-i` = `/install`). "
            "`-d` is `/delete-driver` (`-f` = `/force`). Microsoft keeps them "
            "for old scripts. New commands should use the long names."
        ),
        "examples": [
            "pnputil -e",
            r"pnputil -a -i D:\Drivers\net.inf",
            "pnputil -d -f oem0.inf",
        ],
    },
]


STATUS_LABEL = {
    "ready": "In this app",
    "inspect": "In this app",
    "planned": "UI later",
}

STATUS_COLOR = {
    "ready": "positive",
    "inspect": "positive",
    "planned": "grey",
}


def commands_by_group() -> list[tuple[str, list[PnpCommand]]]:
    grouped: dict[str, list[PnpCommand]] = {g: [] for g in GROUPS}
    for cmd in COMMANDS:
        grouped.setdefault(cmd["group"], []).append(cmd)
    return [(g, grouped[g]) for g in GROUPS if grouped.get(g)]
