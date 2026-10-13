"""
Explorer Advance — PnPUtil

NiceGUI front-end for listing third-party Windows driver packages
and for learning the built-in `pnputil` command. The inventory tab
runs `pnputil /enum-drivers` (CSV) so you can search and sort the
OEM store, including by driver date, and adds read-only `/files`,
`/ids`, and `/enum-devices /problem` for extra detail.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from nicegui import run, ui

import pnp_docs
import pnp_ops

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "user_config.json"
APP_PORT = 8767


@dataclass
class AppConfig:
    sort_key: str = "date_desc"
    in_use_only: bool = False
    older_only: bool = False
    problems_only: bool = False
    last_export_dir: str = ""


def load_config() -> AppConfig:
    if not CONFIG_PATH.is_file():
        return AppConfig()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        known = {f.name for f in AppConfig.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return AppConfig(**{k: v for k, v in data.items() if k in known})
    except Exception:
        return AppConfig()


def save_config(cfg: AppConfig) -> None:
    try:
        CONFIG_PATH.write_text(
            json.dumps(asdict(cfg), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


cfg = load_config()
inventory: Optional[pnp_ops.DriverInventory] = None
problem_inventory: Optional[pnp_ops.ProblemInventory] = None
packages_by_name: dict[str, pnp_ops.DriverPackage] = {}


def _row_from_event(e: Any) -> dict:
    args = getattr(e, "args", e)
    if isinstance(args, list):
        args = args[0] if args else {}
    return args if isinstance(args, dict) else {}


def _copy(text: str, what: str = "Copied") -> None:
    ui.clipboard.write(text)
    ui.notify(what, type="positive")


def _safe_open_explorer(path: str) -> None:
    if not path:
        ui.notify("No path for that package.", type="warning")
        return
    try:
        pnp_ops.open_in_explorer(path)
        ui.notify(f"Opened in Explorer:\n{path}", type="positive")
    except Exception as exc:
        ui.notify(f"Could not open Explorer: {exc}", type="negative")


SORT_OPTIONS = {
    "date_desc": "Newest date first",
    "date_asc": "Oldest date first",
    "provider": "Provider A–Z",
    "class": "Class A–Z",
    "published": "Published name (oem#)",
    "original": "Original INF name",
}


# ---------------------------------------------------------------------------
# Tab 1 — Installed drivers
# ---------------------------------------------------------------------------


def build_drivers_tab() -> None:
    table_columns = [
        {
            "name": "published",
            "label": "Published",
            "field": "published",
            "sortable": True,
            "align": "left",
            "style": "width: 7.5rem",
            "headerStyle": "width: 7.5rem",
        },
        {
            "name": "original",
            "label": "Original INF",
            "field": "original",
            "sortable": True,
            "align": "left",
            "classes": "ellipsis",
            "style": "width: 14rem; max-width: 14rem",
            "headerStyle": "width: 14rem; max-width: 14rem",
        },
        {
            "name": "provider",
            "label": "Provider",
            "field": "provider",
            "sortable": True,
            "align": "left",
            "classes": "ellipsis",
            "style": "width: 14rem; max-width: 14rem",
            "headerStyle": "width: 14rem; max-width: 14rem",
        },
        {
            "name": "class_name",
            "label": "Class",
            "field": "class_name",
            "sortable": True,
            "align": "left",
            "style": "width: 10rem",
            "headerStyle": "width: 10rem",
        },
        {
            "name": "date",
            "label": "Date",
            "field": "date",
            "sortable": True,
            "align": "left",
            "style": "width: 7.5rem",
            "headerStyle": "width: 7.5rem",
        },
        {
            "name": "version",
            "label": "Version",
            "field": "version",
            "sortable": True,
            "align": "left",
            "style": "width: 9rem",
            "headerStyle": "width: 9rem",
        },
        {
            "name": "in_use",
            "label": "In use",
            "field": "in_use",
            "sortable": True,
            "align": "left",
            "style": "width: 5.5rem",
            "headerStyle": "width: 5.5rem",
        },
        {
            "name": "actions",
            "label": "",
            "field": "actions",
            "align": "right",
            "required": True,
            "style": "width: 8rem",
            "headerStyle": "width: 8rem",
        },
    ]

    state: dict[str, Any] = {
        "packages": [],
        "class": "",
        "provider": "",
        "query": "",
        "loading": False,
    }

    with ui.column().classes("w-full max-w-[96rem] mx-auto p-4 gap-4"):
        with ui.card().classes("w-full"):
            ui.markdown(
                "**Third-party driver packages** currently in the Windows "
                "driver store (`pnputil /enum-drivers`). This is the OEM "
                "list — in-box Microsoft drivers are not included. Search "
                "by name, provider, class, device or **file**; sort by **date** "
                "(newest first by default). Package details include files "
                "(`/files`) and store IDs (`/ids`). **Problem devices** is "
                "`pnputil /enum-devices /problem` — Device Manager’s yellow "
                "triangles, including in-box drivers."
            )
            cmd_label = ui.label(
                "Will run: pnputil /enum-drivers /devices /format csv "
                "· /files · /ids · /enum-devices /problem"
            ).classes("text-caption text-grey-8 mt-2 font-mono")

        with ui.card().classes("w-full"):
            ui.label("Filter & sort").classes("text-subtitle1 font-bold")
            with ui.row().classes("w-full items-end gap-3 flex-wrap"):
                w_query = (
                    ui.input(
                        "Search",
                        placeholder="oem17, NVIDIA, Display, Realtek…",
                    )
                    .props("clearable debounce=200 outlined dense")
                    .classes("w-72")
                )
                w_class = ui.select(
                    options={"": "All classes"},
                    value="",
                    label="Class",
                    with_input=True,
                ).classes("w-56").props("dense outlined clearable")
                w_provider = ui.select(
                    options={"": "All providers"},
                    value="",
                    label="Provider",
                    with_input=True,
                ).classes("w-64").props("dense outlined clearable")
                w_sort = ui.select(
                    options=SORT_OPTIONS,
                    value=cfg.sort_key if cfg.sort_key in SORT_OPTIONS else "date_desc",
                    label="Sort",
                ).classes("w-56").props("dense outlined")

            with ui.row().classes("w-full flex-wrap gap-4 items-center"):
                w_in_use = ui.checkbox(
                    "Only packages in use by a device",
                    value=cfg.in_use_only,
                )
                w_older = ui.checkbox(
                    "Only older copies (same original INF, older date)",
                    value=cfg.older_only,
                ).tooltip(
                    "Several oem#.inf files can share one original name. "
                    "This keeps the older ones — useful before a cleanup."
                )
                w_problems = ui.checkbox(
                    "Only packages bound to a device with a problem",
                    value=cfg.problems_only,
                ).tooltip(
                    "Keeps OEM packages whose bound devices report a "
                    "Device Manager problem code."
                )

            chips = ui.row().classes("flex-wrap gap-1")

        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center gap-3 flex-wrap"):
                refresh_btn = ui.button(
                    "Refresh drivers",
                    icon="refresh",
                    on_click=lambda: None,
                ).props("unelevated size=lg")
                ui.button(
                    "Save settings",
                    icon="save",
                    on_click=lambda: persist_settings(),
                ).props("flat")
                problems_btn = (
                    ui.button(
                        "Problem devices",
                        icon="error_outline",
                        on_click=lambda: show_problem_dialog(),
                    )
                    .props("outline")
                    .tooltip(
                        "pnputil /enum-devices /problem — yellow triangles "
                        "from Device Manager, including in-box drivers"
                    )
                )

            progress = ui.linear_progress(show_value=False).classes("w-full")
            progress.visible = False
            status = ui.label("Loading driver store…").classes("text-caption text-grey-8")

        with ui.card().classes("w-full mb-16"):
            with ui.row().classes("w-full items-center justify-between flex-wrap gap-2"):
                with ui.column().classes("gap-0"):
                    summary = ui.label("No inventory yet.").classes("text-subtitle2")
                    ui.label(
                        "Check rows for the action bar. Click a column header "
                        "to re-sort the visible page."
                    ).classes("text-caption text-grey-7")
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    selection_chip = (
                        ui.button(
                            "Actions",
                            icon="checklist",
                            on_click=lambda: show_selection_dock(),
                        )
                        .props("unelevated")
                        .tooltip("Show the action bar for the checked items")
                    )
                    selection_chip.visible = False
                    filter_input = (
                        ui.input(placeholder="Filter table…")
                        .props("dense clearable debounce=200")
                        .classes("w-56")
                    )

            table = (
                ui.table(
                    columns=table_columns,
                    rows=[],
                    row_key="published",
                    selection="multiple",
                    pagination=25,
                )
                .classes("w-full")
                .props('table-style="table-layout: fixed; width: 100%"')
            )
            table.add_slot(
                "body-cell-published",
                """
                <q-td :props="props">
                    <div class="ellipsis font-mono">{{ props.row.published }}</div>
                    <q-badge v-if="props.row.duplicate === 'older'"
                             color="orange-8" outline
                             class="q-mt-xs cursor-pointer"
                             @click.stop="$parent.$emit('show_siblings', props.row)">
                        Older copy
                        <q-tooltip>Click to see the other versions in the store</q-tooltip>
                    </q-badge>
                    <q-badge v-else-if="props.row.duplicate === 'latest'"
                             color="primary" outline
                             class="q-mt-xs cursor-pointer"
                             @click.stop="$parent.$emit('show_siblings', props.row)">
                        Latest of {{ props.row.sibling_count }}
                        <q-tooltip>Click to see the other versions in the store</q-tooltip>
                    </q-badge>
                </q-td>
                """,
            )
            table.add_slot(
                "body-cell-original",
                """
                <q-td :props="props">
                    <div class="ellipsis">{{ props.row.original }}</div>
                    <q-tooltip class="text-body2" max-width="36rem">
                        {{ props.row.original }}
                    </q-tooltip>
                </q-td>
                """,
            )
            table.add_slot(
                "body-cell-provider",
                """
                <q-td :props="props">
                    <div class="ellipsis">{{ props.row.provider }}</div>
                    <q-tooltip class="text-body2" max-width="36rem">
                        {{ props.row.provider }}
                    </q-tooltip>
                </q-td>
                """,
            )
            table.add_slot(
                "body-cell-in_use",
                """
                <q-td :props="props">
                    <q-icon
                        :name="props.row.in_use === 'Yes' ? 'check_circle' : 'radio_button_unchecked'"
                        :color="props.row.has_problem ? 'negative' : (props.row.in_use === 'Yes' ? 'positive' : 'grey')"
                        size="sm"
                        class="q-mr-xs"
                    />
                    <span>{{ props.row.in_use }}</span>
                    <div v-if="props.row.device_summary"
                         class="text-caption text-grey-7 ellipsis">
                        {{ props.row.device_summary }}
                    </div>
                </q-td>
                """,
            )
            table.add_slot(
                "body-cell-actions",
                """
                <q-td :props="props" style="width: 8rem; white-space: nowrap;">
                    <q-btn flat dense round icon="info" color="secondary"
                           @click.stop="$parent.$emit('show_info', props.row)">
                        <q-tooltip>Package details</q-tooltip>
                    </q-btn>
                    <q-btn flat dense round icon="folder_open" color="primary"
                           @click.stop="$parent.$emit('open_explorer', props.row)">
                        <q-tooltip>Reveal oem INF in Explorer</q-tooltip>
                    </q-btn>
                    <q-btn flat dense round icon="content_copy"
                           @click.stop="$parent.$emit('copy_name', props.row)">
                        <q-tooltip>Copy published name</q-tooltip>
                    </q-btn>
                </q-td>
                """,
            )
            filter_input.bind_value(table, "filter")

            with ui.row().classes("w-full items-center gap-2 flex-wrap"):
                ui.button(
                    "Details",
                    icon="info",
                    on_click=lambda: act_selected("info"),
                ).props("outline color=secondary")
                ui.button(
                    "Reveal INF",
                    icon="folder_open",
                    on_click=lambda: act_selected("open"),
                ).props("unelevated")
                ui.button(
                    "Copy names",
                    icon="content_copy",
                    on_click=lambda: act_selected("copy"),
                ).props("flat")
                ui.button(
                    "Export selected",
                    icon="ios_share",
                    on_click=lambda: act_selected("export"),
                ).props("outline").tooltip(
                    "pnputil /export-driver — copies packages out of the store"
                )
                ui.button(
                    "Clear selection",
                    icon="deselect",
                    on_click=lambda: clear_selection(),
                ).props("flat")

        def persist_settings(*, notify: bool = True) -> None:
            cfg.sort_key = str(w_sort.value or "date_desc")
            cfg.in_use_only = bool(w_in_use.value)
            cfg.older_only = bool(w_older.value)
            cfg.problems_only = bool(w_problems.value)
            save_config(cfg)
            if notify:
                ui.notify("Settings saved", type="positive")

        def selected_rows() -> list[dict]:
            return list(table.selected or [])

        def require_selection() -> list[dict]:
            rows = selected_rows()
            if not rows:
                ui.notify("Check one or more rows first.", type="warning")
            return rows

        def package_for(row: dict) -> Optional[pnp_ops.DriverPackage]:
            name = str(row.get("published") or "")
            return packages_by_name.get(name)

        selection_ui = {"dock_hidden": False}

        def _selection_preview(rows: list[dict], *, limit: int = 4) -> str:
            names = [str(row.get("published") or "") for row in rows]
            names = [name for name in names if name]
            if not names:
                return ""
            text = " · ".join(names[:limit])
            extra = len(names) - limit
            if extra > 0:
                text += f"  +{extra:,} more"
            return text

        def refresh_selection_ui() -> None:
            if sel_title.is_deleted:
                return
            rows = selected_rows()
            count = len(rows)
            if count == 0:
                sel_title.set_text("No packages selected")
                sel_names.set_text("")
                selection_chip.visible = False
                selection_dock.visible = False
                return
            label = (
                "1 package selected" if count == 1 else f"{count:,} packages selected"
            )
            sel_title.set_text(label)
            sel_names.set_text(_selection_preview(rows))
            selection_chip.set_text(f"{label} — Actions")
            selection_chip.visible = True
            selection_dock.visible = not selection_ui["dock_hidden"]

        def show_selection_dock() -> None:
            if not selected_rows():
                ui.notify("Check one or more rows first.", type="warning")
                return
            selection_ui["dock_hidden"] = False
            refresh_selection_ui()

        def hide_selection_dock() -> None:
            selection_ui["dock_hidden"] = True
            selection_dock.visible = False

        def on_table_select(_e=None) -> None:
            if not selected_rows():
                selection_ui["dock_hidden"] = False
            refresh_selection_ui()

        def clear_selection() -> None:
            table.selected = []
            selection_ui["dock_hidden"] = False
            refresh_selection_ui()

        table.on_select(on_table_select)

        with ui.element("div").classes(
            "fixed left-0 right-0 bottom-0 z-[4000] flex justify-center p-3 pointer-events-none"
        ) as selection_dock:
            with ui.card().classes("pointer-events-auto shadow-2xl").style(
                "box-shadow: 0 10px 32px rgba(21, 101, 192, 0.28);"
            ):
                with ui.row().classes("items-center gap-3 flex-wrap"):
                    with ui.column().classes("gap-0 min-w-[10rem] max-w-[22rem]"):
                        sel_title = ui.label("No packages selected").classes(
                            "text-subtitle2 font-bold"
                        )
                        sel_names = ui.label("").classes(
                            "text-caption text-grey-8 break-all"
                        )
                    ui.button(
                        "Details",
                        icon="info",
                        on_click=lambda: act_selected("info"),
                    ).props("outline color=secondary")
                    ui.button(
                        "Reveal INF",
                        icon="folder_open",
                        on_click=lambda: act_selected("open"),
                    ).props("unelevated")
                    ui.button(
                        "Copy names",
                        icon="content_copy",
                        on_click=lambda: act_selected("copy"),
                    ).props("flat")
                    ui.button(
                        "Export selected",
                        icon="ios_share",
                        on_click=lambda: act_selected("export"),
                    ).props("outline")
                    ui.button(
                        "Clear selection",
                        icon="deselect",
                        on_click=lambda: clear_selection(),
                    ).props("flat")
                    ui.button(icon="close", on_click=hide_selection_dock).props(
                        "flat round dense"
                    ).tooltip("Hide this bar")
        selection_dock.visible = False

        def apply_visible() -> None:
            pkgs: list[pnp_ops.DriverPackage] = state["packages"]
            visible = pnp_ops.filter_packages(
                pkgs,
                query=str(w_query.value or ""),
                class_name=str(w_class.value or ""),
                provider=str(w_provider.value or ""),
                in_use_only=bool(w_in_use.value),
                older_only=bool(w_older.value),
                problems_only=bool(w_problems.value),
            )
            visible = pnp_ops.sort_packages(
                visible, key=str(w_sort.value or "date_desc")
            )
            selected = {
                str(row.get("published")) for row in selected_rows() if row.get("published")
            }
            rows = [pkg.to_row() for pkg in visible]
            table.rows = rows
            table.selected = [row for row in rows if row["published"] in selected]
            n = len(rows)
            used = sum(1 for pkg in visible if pkg.in_use)
            older = sum(1 for pkg in visible if pkg.duplicate == "older")
            troubled = sum(1 for pkg in visible if pkg.has_problem)
            total = len(pkgs)
            extra_bits = []
            if older:
                extra_bits.append(
                    f"{older:,} older cop{'y' if older == 1 else 'ies'}"
                    if n == total
                    else f"{older:,} older"
                )
            if troubled:
                extra_bits.append(
                    f"{troubled:,} with a device problem"
                )
            extra = (", " + ", ".join(extra_bits)) if extra_bits else ""
            if n == total:
                summary.set_text(
                    f"{n:,} OEM package(s) — {used:,} in use{extra}."
                )
            else:
                summary.set_text(
                    f"Showing {n:,} of {total:,} — {used:,} in use{extra}."
                )
            refresh_selection_ui()

        def render_class_chips() -> None:
            chips.clear()
            counts: dict[str, int] = {}
            for pkg in state["packages"]:
                if pkg.class_name:
                    counts[pkg.class_name] = counts.get(pkg.class_name, 0) + 1
            if not counts:
                return
            with chips:
                ui.label("Classes:").classes("text-caption text-grey-8 self-center")
                for name in sorted(counts, key=str.casefold):

                    def make_click(class_name: str):
                        def _click() -> None:
                            w_class.value = "" if w_class.value == class_name else class_name
                            apply_visible()

                        return _click

                    color = "primary" if w_class.value == name else "grey"
                    ui.badge(
                        f"{name} ({counts[name]})",
                        color=color,
                    ).props("outline").classes("cursor-pointer").on(
                        "click", make_click(name)
                    )

        def apply_filter_options(pkgs: list[pnp_ops.DriverPackage]) -> None:
            classes = {"": "All classes"}
            for name in pnp_ops.classes_from(pkgs):
                classes[name] = name
            providers = {"": "All providers"}
            for name in pnp_ops.providers_from(pkgs):
                providers[name] = name
            w_class.options = classes
            w_provider.options = providers
            if w_class.value not in classes:
                w_class.value = ""
            if w_provider.value not in providers:
                w_provider.value = ""
            render_class_chips()

        def refresh_problem_button() -> None:
            count = len(problem_inventory.devices) if problem_inventory else 0
            if count == 0:
                problems_btn.set_text("Problem devices")
            elif count == 1:
                problems_btn.set_text("1 problem device")
            else:
                problems_btn.set_text(f"{count:,} problem devices")

        async def load_drivers(*, notify: bool = False) -> None:
            global inventory, problem_inventory, packages_by_name
            if state["loading"]:
                return
            state["loading"] = True
            persist_settings(notify=False)
            refresh_btn.disable()
            progress.visible = True
            progress.props("indeterminate")
            status.set_text("Running pnputil /enum-drivers…")

            try:
                result, problems = await run.io_bound(pnp_ops.load_inspect)
            except Exception as exc:
                status.set_text(f"Failed: {exc}")
                ui.notify(str(exc), type="negative")
                state["loading"] = False
                progress.visible = False
                refresh_btn.enable()
                return

            inventory = result
            problem_inventory = problems
            packages_by_name = {pkg.published: pkg for pkg in result.packages}
            state["packages"] = result.packages
            extra_bits = []
            if any("/files" in cmd for cmd in result.extra_commands):
                extra_bits.append("/files")
            if any("/ids" in cmd for cmd in result.extra_commands):
                extra_bits.append("/ids")
            if problems.command:
                extra_bits.append("/enum-devices /problem")
            cmd_label.set_text(
                "Last command: "
                + result.command
                + (("  ·  " + "  ·  ".join(extra_bits)) if extra_bits else "")
            )
            apply_filter_options(result.packages)
            apply_visible()
            refresh_problem_button()

            extra = f" · format {result.format_used}" if result.format_used else ""
            problem_bit = (
                f" · {len(problems.devices):,} problem device(s)"
                if problems.devices
                else " · no problem devices"
            )
            if result.error:
                status.set_text(result.error.splitlines()[0])
                ui.notify(result.error, type="negative", multi_line=True)
            else:
                status.set_text(
                    f"Loaded {len(result.packages):,} OEM package(s){extra}{problem_bit}."
                )
                if notify:
                    ui.notify(
                        f"Loaded {len(result.packages):,} driver package(s).",
                        type="positive",
                    )
            if problems.error:
                ui.notify(problems.error, type="warning", multi_line=True)

            state["loading"] = False
            progress.visible = False
            refresh_btn.enable()

        def on_filter_change(_e=None) -> None:
            apply_visible()
            render_class_chips()

        w_query.on("update:model-value", on_filter_change)
        w_class.on("update:model-value", on_filter_change)
        w_provider.on("update:model-value", on_filter_change)
        w_sort.on("update:model-value", on_filter_change)
        w_in_use.on_value_change(on_filter_change)
        w_older.on_value_change(on_filter_change)
        w_problems.on_value_change(on_filter_change)
        w_query.on("keydown.enter", lambda: apply_visible())

        async def start_export(rows: list[dict]) -> None:
            names = [str(row.get("published")) for row in rows if row.get("published")]
            if not names:
                ui.notify("Check one or more rows first.", type="warning")
                return
            dest = pnp_ops.pick_folder(cfg.last_export_dir)
            if not dest:
                return
            cfg.last_export_dir = dest
            save_config(cfg)
            status.set_text(f"Exporting {len(names):,} package(s) to {dest}…")
            result = await run.io_bound(pnp_ops.export_drivers, names, dest)
            if result.ok:
                status.set_text(f"Exported {len(names):,} package(s) to {dest}.")
                ui.notify(f"Exported {len(names):,} package(s).", type="positive")
            else:
                status.set_text("Export finished with errors (often needs Administrator).")
                ui.notify(
                    result.text or "Export failed. Try an elevated prompt.",
                    type="warning",
                    multi_line=True,
                )
            show_text_dialog(
                f"Export — {len(names):,} package(s)",
                result.text or "(no pnputil output)",
                result.command,
            )

        def act_selected(action: str) -> None:
            rows = require_selection()
            if not rows:
                return
            if action == "open":
                for row in rows[:8]:
                    _safe_open_explorer(str(row.get("inf_path") or ""))
            elif action == "copy":
                names = [str(row.get("published")) for row in rows if row.get("published")]
                _copy("\n".join(names), f"{len(names)} name(s) copied")
            elif action == "info":
                show_package_dialog(rows)
            elif action == "export":
                async def _export() -> None:
                    await start_export(rows)

                ui.timer(0.05, _export, once=True)

        refresh_btn.on_click(lambda: load_drivers(notify=True))
        table.on("show_info", lambda e: show_package_dialog([_row_from_event(e)]))
        table.on("show_siblings", lambda e: show_sibling_dialog(_row_from_event(e)))
        table.on("copy_name", lambda e: _copy(
            str(_row_from_event(e).get("published") or ""),
            "Published name copied",
        ))
        table.on(
            "open_explorer",
            lambda e: _safe_open_explorer(str(_row_from_event(e).get("inf_path") or "")),
        )
        table.on(
            "rowDblclick",
            lambda e: show_package_dialog([_row_from_event(e)]),
        )

        ui.timer(0.05, load_drivers, once=True)


def show_text_dialog(title: str, body: str, command: str = "") -> None:
    with ui.dialog() as dialog, ui.card().classes("w-[820px] max-w-[95vw]"):
        ui.label(title).classes("text-subtitle1 font-bold")
        if command:
            ui.code(command).classes("w-full")
        ui.code(body).classes("w-full")
        with ui.row().classes("w-full justify-end"):
            ui.button("Close", on_click=dialog.close).props("flat")
    dialog.open()


def show_sibling_dialog(row: dict) -> None:
    original = str(row.get("original") or "").strip()
    clicked = str(row.get("published") or "").strip()
    if not original:
        ui.notify("This package has no original INF name to group by.", type="warning")
        return
    pool = (
        list(inventory.packages)
        if inventory is not None
        else list(packages_by_name.values())
    )
    siblings = pnp_ops.siblings_of(pool, original=original)
    if len(siblings) < 2:
        ui.notify(f"No other packages share {original}.", type="info")
        return

    with ui.dialog() as dialog, ui.card().classes("w-[860px] max-w-[95vw]"):
        ui.label(f"Versions of {original}").classes("text-subtitle1 font-bold")
        ui.markdown(
            "Windows can keep **several OEM packages** that came from the same "
            "original INF — an older Realtek audio next to a newer one, for "
            "example. This app ranks them by **driver date**, then version. "
            f"**Latest of {len(siblings)}** is the newest copy. Live devices "
            "usually bind to that one. The older copies stay in the store "
            "until you delete them (not wired in this app)."
        )
        with ui.column().classes("w-full gap-2"):
            for pkg in siblings:
                is_clicked = pkg.published == clicked
                with ui.card().classes(
                    "w-full " + ("bg-blue-1" if is_clicked else "")
                ):
                    with ui.row().classes(
                        "w-full items-center justify-between gap-3 flex-wrap"
                    ):
                        with ui.column().classes("gap-0"):
                            with ui.row().classes("items-center gap-2 flex-wrap"):
                                ui.label(pkg.published).classes(
                                    "text-subtitle2 font-mono"
                                )
                                if pkg.duplicate == "latest":
                                    ui.badge(
                                        f"Latest of {pkg.sibling_count}",
                                        color="primary",
                                    ).props("outline")
                                elif pkg.duplicate == "older":
                                    ui.badge("Older copy", color="orange-8").props(
                                        "outline"
                                    )
                                if pkg.in_use:
                                    ui.badge("In use", color="positive").props(
                                        "outline"
                                    )
                                if is_clicked:
                                    ui.badge("This row", color="grey").props("outline")
                            bits = [
                                pkg.driver_date or "no date",
                                pkg.version or "no version",
                                pkg.provider or "",
                            ]
                            ui.label("  ·  ".join(b for b in bits if b)).classes(
                                "text-caption text-grey-8"
                            )
                        ui.button(
                            "Details",
                            icon="info",
                            on_click=lambda _e, name=pkg.published: show_package_dialog(
                                [{"published": name}]
                            ),
                        ).props("outline dense")
        with ui.row().classes("w-full justify-end"):
            ui.button("Close", on_click=dialog.close).props("flat")
    dialog.open()


def show_package_dialog(rows: list[dict]) -> None:
    rows = [row for row in rows if row.get("published")]
    if not rows:
        return

    current = {"name": str(rows[0]["published"])}
    shown = rows[:40]

    with ui.dialog() as dialog, ui.card().classes("w-[860px] max-w-[95vw]"):
        if len(rows) > 1:
            ui.label(f"Driver package — {len(rows):,} selected").classes(
                "text-subtitle1 font-bold"
            )
            picker = ui.select(
                options=[str(r["published"]) for r in shown],
                value=current["name"],
                label="Package",
                with_input=len(shown) > 8,
            ).classes("w-full")
            if len(rows) > 40:
                ui.label(f"Showing the first 40 of {len(rows):,} selected.").classes(
                    "text-caption text-grey-8"
                )
        else:
            picker = None
            ui.label("Driver package").classes("text-subtitle1 font-bold")

        title = ui.label("").classes("text-subtitle2")
        meta = ui.column().classes("w-full gap-1")
        devices_host = ui.column().classes("w-full gap-1")
        cmds = ui.column().classes("w-full gap-1")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(
                "Reveal INF",
                icon="folder_open",
                on_click=lambda: _safe_open_explorer(
                    (packages_by_name.get(current["name"]).inf_path)
                    if packages_by_name.get(current["name"])
                    else ""
                ),
            ).props("outline").tooltip("C:\\Windows\\INF\\oem#.inf")
            ui.button(
                "Reveal store folder",
                icon="inventory_2",
                on_click=lambda: _safe_open_explorer(
                    (packages_by_name.get(current["name"]).store_path)
                    if packages_by_name.get(current["name"])
                    else ""
                ),
            ).props("outline").tooltip(
                "Driver store FileRepository folder for this package"
            )
            ui.button("Close", on_click=dialog.close).props("flat")

        def fill(name: str) -> None:
            pkg = packages_by_name.get(name)
            if pkg is None:
                title.set_text(name)
                return
            title.set_text(f"{pkg.published}  ·  {pkg.original or '—'}")
            meta.clear()
            with meta:
                facts = [
                    ("Provider", pkg.provider or "—"),
                    ("Class", pkg.class_name or "—"),
                    ("Class GUID", pkg.class_guid or "—"),
                    ("Date", pkg.driver_date or "—"),
                    ("Version", pkg.version or "—"),
                    ("Signer", pkg.signer or "—"),
                    ("Catalog attributes", pkg.catalog or "—"),
                    ("Catalog file", pkg.catalog_file or "—"),
                    ("Package ID", pkg.package_id or "—"),
                    ("Family ID", pkg.family_id or "—"),
                    ("Published INF", pkg.inf_path or "—"),
                    ("Store folder", pkg.store_path or "—"),
                ]
                if pkg.extension_id:
                    facts.append(("Extension ID", pkg.extension_id))
                if pkg.duplicate:
                    label = (
                        f"Latest of {pkg.sibling_count} packages with this original INF"
                        if pkg.duplicate == "latest"
                        else f"Older copy — {pkg.sibling_count} packages share {pkg.original}"
                    )
                    facts.append(("Duplicates", label))
                for label, value in facts:
                    with ui.row().classes("w-full no-wrap gap-3"):
                        ui.label(label).classes("text-caption text-grey-7 w-32 shrink-0")
                        ui.label(value).classes("text-body2 break-all")
                if pkg.duplicate and pkg.original:
                    ui.button(
                        "Show other versions",
                        icon="layers",
                        on_click=lambda _e, name=pkg.published, orig=pkg.original: show_sibling_dialog(
                            {"published": name, "original": orig}
                        ),
                    ).props("outline dense")

            devices_host.clear()
            with devices_host:
                ui.label("Devices using this package").classes("text-subtitle2 mt-2")
                if not pkg.devices:
                    ui.label(
                        "None reported. Either nothing is bound to it, or this "
                        "Windows build’s pnputil did not return /devices."
                    ).classes("text-caption text-grey-7")
                else:
                    for dev in pkg.devices:
                        mark = "warning" if dev.has_problem else "positive"
                        line = dev.description or dev.instance_id
                        extra = f" — {dev.status}" if dev.status else ""
                        if dev.has_problem:
                            extra += " · " + pnp_ops.format_problem_code(dev.problem_code)
                        ui.badge(line + extra, color=mark).props("outline")
                        if dev.instance_id and dev.description:
                            ui.label(dev.instance_id).classes(
                                "text-caption text-grey-7 font-mono -mt-1"
                            )

            cmds.clear()
            with cmds:
                ui.label("Files in this package").classes("text-subtitle2 mt-2")
                file_names = list(pkg.files)
                if pkg.catalog_file and pkg.catalog_file not in file_names:
                    file_names = [pkg.catalog_file, *file_names]
                if not file_names:
                    ui.label(
                        "None reported. This Windows build’s pnputil may not "
                        "support `/enum-drivers /files`."
                    ).classes("text-caption text-grey-7")
                else:
                    ui.label(
                        f"{len(file_names):,} file(s) from `pnputil /enum-drivers /files`."
                    ).classes("text-caption text-grey-7")
                    with ui.scroll_area().classes("w-full").style("max-height: 12rem"):
                        for name in file_names:
                            tag = "  (catalog)" if name == pkg.catalog_file else ""
                            ui.label(name + tag).classes("text-caption font-mono")
                    ui.button(
                        "Copy file list",
                        icon="content_copy",
                        on_click=lambda _e, names=file_names: _copy(
                            "\n".join(names), f"{len(names)} file name(s) copied"
                        ),
                    ).props("flat dense")

                ui.label("Useful commands").classes("text-subtitle2 mt-2")
                examples = [
                    f"pnputil /export-driver {pkg.published} .",
                    f"pnputil /delete-driver {pkg.published} /uninstall",
                    "pnputil /enum-drivers /files",
                    "pnputil /enum-devices /problem",
                ]
                for ex in examples:
                    with ui.row().classes("w-full items-start gap-2"):
                        ui.code(ex).classes("flex-grow")
                        ui.button(
                            icon="content_copy",
                            on_click=lambda _e, example=ex: _copy(example),
                        ).props("flat dense round")

        if picker is not None:
            picker.on(
                "update:model-value",
                lambda e: (current.update(name=e.args or picker.value), fill(current["name"])),
            )
        fill(current["name"])

    dialog.open()


def show_problem_dialog() -> None:
    problems = problem_inventory
    devices = list(problems.devices) if problems else []
    command = problems.command if problems else "pnputil /enum-devices /problem /format csv"
    error = problems.error if problems else ""

    with ui.dialog() as dialog, ui.card().classes("w-[860px] max-w-[95vw]"):
        ui.label("Problem devices").classes("text-subtitle1 font-bold")
        ui.markdown(
            "`pnputil /enum-devices /problem` — the same yellow triangles as "
            "Device Manager. This includes in-box Microsoft drivers, not only "
            "OEM packages."
        )
        ui.code(command).classes("w-full")
        if error:
            ui.label(error).classes("text-caption text-negative")
        if not devices:
            ui.label("No devices currently report a problem.").classes(
                "text-body2 text-grey-8"
            )
        else:
            ui.label(
                f"{len(devices):,} device(s) with a problem code."
            ).classes("text-caption text-grey-7")
            with ui.scroll_area().classes("w-full").style("max-height: 28rem"):
                for dev in devices:
                    with ui.card().classes("w-full"):
                        title = dev.description or dev.instance_id
                        ui.label(title).classes("text-subtitle2")
                        facts = [
                            ("Instance ID", dev.instance_id or "—"),
                            ("Class", dev.class_name or "—"),
                            ("Manufacturer", dev.manufacturer or "—"),
                            ("Status", dev.status or "—"),
                            ("Problem", pnp_ops.format_problem_code(dev.problem_code)),
                            ("Driver", dev.driver_name or "—"),
                        ]
                        if dev.extension_drivers:
                            facts.append(("Extensions", dev.extension_drivers))
                        if dev.problem_status:
                            facts.append(("Problem status", dev.problem_status))
                        for label, value in facts:
                            with ui.row().classes("w-full no-wrap gap-3"):
                                ui.label(label).classes(
                                    "text-caption text-grey-7 w-32 shrink-0"
                                )
                                ui.label(value).classes("text-body2 break-all font-mono")
                        oem = (dev.driver_name or "").strip()
                        if oem in packages_by_name:
                            ui.button(
                                f"Open {oem}",
                                icon="info",
                                on_click=lambda _e, name=oem: show_package_dialog(
                                    [{"published": name}]
                                ),
                            ).props("outline dense")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(
                "Copy listing",
                icon="content_copy",
                on_click=lambda: _copy(
                    problems.raw if problems and problems.raw else command,
                    "Problem listing copied",
                ),
            ).props("flat")
            ui.button("Close", on_click=dialog.close).props("flat")
    dialog.open()


# ---------------------------------------------------------------------------
# Tab 2 — Manual
# ---------------------------------------------------------------------------


def _manual_command_row(command: str) -> None:
    with ui.row().classes("w-full items-start gap-2 no-wrap"):
        ui.code(command).classes("flex-grow")
        ui.button(
            icon="content_copy",
            on_click=lambda _e, example=command: _copy(example),
        ).props("flat dense round").tooltip("Copy command")


def _manual_kv_row(left: str, right: str, *, mono_left: bool = True) -> None:
    with ui.row().classes("w-full items-start gap-6 py-2 flex-wrap"):
        if mono_left:
            ui.code(left).classes("w-[22rem] max-w-full")
        else:
            ui.label(left).classes("w-[22rem] max-w-full text-subtitle2")
        ui.markdown(right).classes("flex-grow text-body2 pnp-manual-copy min-w-[16rem]")


def build_manual_tab() -> None:
    ui.add_css(
        """
        .pnp-manual .q-markdown p { line-height: 1.7; margin: 0 0 0.85rem; }
        .pnp-manual .q-markdown p:last-child { margin-bottom: 0; }
        .pnp-manual .q-markdown ul { margin: 0.35rem 0 0; padding-left: 1.2rem; }
        .pnp-manual .q-markdown li { margin: 0.45rem 0; line-height: 1.65; }
        .pnp-manual .q-markdown code { font-size: 0.9em; }
        .pnp-manual .pnp-manual-copy p { margin: 0; line-height: 1.65; }
        .pnp-manual .q-expansion-item { border-radius: 8px; }
        .pnp-manual .pnp-anchor { scroll-margin-top: 6rem; }
        """
    )
    anchors: dict[str, Any] = {}

    def jump(key: str) -> None:
        el = anchors.get(key)
        if el is None:
            return
        ui.run_javascript(
            f"const el = getHtmlElement({el.id});"
            "if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});"
        )

    def make_jump(key: str):
        def _jump() -> None:
            jump(key)

        return _jump

    with ui.column().classes(
        "pnp-manual w-full max-w-[96rem] mx-auto px-8 py-8 gap-8"
    ):
        with ui.card().classes("w-full p-6 pnp-anchor") as top_card:
            anchors["top"] = top_card
            ui.label("PnPUtil manual").classes("text-h6")
            ui.markdown(
                "A field guide to **`pnputil.exe`**, the Windows command that "
                "manages the **driver store** and devices. Start with **How "
                "drivers work** if `oem#.inf` and “Latest of 3” are new. "
                "Switches match `pnputil /?` on this PC — including newer ones "
                "(`/enum-devicetree`, `/enum-containers`, `/format`, `/force`)."
            ).classes("text-body1")
            with ui.row().classes("gap-2 flex-wrap mt-2"):
                for key, label, icon in (
                    ("beginner", "How drivers work", "school"),
                    ("overview", "Overview", "info"),
                    ("quick", "Quick start", "play_circle"),
                    ("safety", "Safety", "health_and_safety"),
                    ("switches", "Switch list", "list"),
                    ("compare", "Compared to", "compare_arrows"),
                ):
                    ui.button(
                        label,
                        icon=icon,
                        on_click=make_jump(key),
                    ).props("flat dense").tooltip(f"Jump to {label}")

        with ui.card().classes("w-full p-6 pnp-anchor") as beginner_card:
            anchors["beginner"] = beginner_card
            with ui.column().classes("w-full gap-5"):
                ui.label("How drivers work").classes("text-subtitle1 font-bold")
                ui.label(
                    "A short tour for anyone who has not lived in Device Manager. "
                    "No commands yet — those come in Quick start."
                ).classes("text-body2 text-grey-8")
                for index, (title, body) in enumerate(
                    pnp_docs.BEGINNER_SECTIONS, start=1
                ):
                    if index > 1:
                        ui.separator()
                    with ui.row().classes("w-full items-start gap-4 no-wrap"):
                        ui.badge(str(index), color="primary").props("rounded")
                        with ui.column().classes("gap-1 flex-grow"):
                            ui.label(title).classes("text-subtitle2")
                            ui.markdown(body).classes("pnp-manual-copy text-grey-9")

        with ui.card().classes("w-full p-6 pnp-anchor") as overview_card:
            anchors["overview"] = overview_card
            with ui.column().classes("w-full gap-6"):
                ui.label("Overview").classes("text-subtitle1 font-bold")
                with ui.column().classes("w-full gap-2"):
                    ui.label("What pnputil is").classes("text-subtitle2")
                    ui.markdown(pnp_docs.OVERVIEW_WHAT_MD)
                ui.separator()
                with ui.column().classes("w-full gap-2"):
                    ui.label("The driver store").classes("text-subtitle2")
                    ui.markdown(pnp_docs.OVERVIEW_STORE_MD)
                ui.separator()
                with ui.column().classes("w-full gap-3"):
                    ui.label("Golden rules").classes("text-subtitle2")
                    for index, (title, body) in enumerate(pnp_docs.GOLDEN_RULES, start=1):
                        with ui.row().classes("w-full items-start gap-4 no-wrap"):
                            ui.badge(str(index), color="primary").props("rounded")
                            with ui.column().classes("gap-1 flex-grow"):
                                ui.label(title).classes("text-subtitle2")
                                ui.markdown(body).classes("pnp-manual-copy text-grey-9")

        with ui.card().classes("w-full p-6 pnp-anchor") as quick_card:
            anchors["quick"] = quick_card
            with ui.column().classes("w-full gap-5"):
                ui.label("Quick start").classes("text-subtitle1 font-bold")
                ui.label(
                    "Seven commands that cover the usual driver-store work. "
                    "Copy any line into a prompt — listing needs no elevation."
                ).classes("text-body2 text-grey-8")
                for index, step in enumerate(pnp_docs.QUICKSTART_STEPS, start=1):
                    if index > 1:
                        ui.separator()
                    with ui.row().classes("w-full items-start gap-4 no-wrap"):
                        ui.badge(str(index), color="primary").props("rounded")
                        with ui.column().classes("gap-2 flex-grow min-w-0"):
                            ui.label(str(step["title"])).classes("text-subtitle2")
                            for command in step["commands"]:
                                _manual_command_row(str(command))
                            ui.markdown(str(step["note"])).classes(
                                "pnp-manual-copy text-grey-9"
                            )

        with ui.card().classes("w-full p-6 pnp-anchor") as safety_card:
            anchors["safety"] = safety_card
            with ui.column().classes("w-full gap-6"):
                ui.label("Safety").classes("text-subtitle1 font-bold")
                with ui.column().classes("w-full gap-3"):
                    with ui.row().classes("items-center gap-2"):
                        ui.badge("Safe to run anytime", color="positive")
                    for command, why in pnp_docs.SAFE_COMMANDS:
                        _manual_kv_row(command, why)
                ui.separator()
                with ui.column().classes("w-full gap-3"):
                    with ui.row().classes("items-center gap-2"):
                        ui.badge("Needs a clear intent", color="orange-8")
                    for command, why in pnp_docs.INTENT_COMMANDS:
                        _manual_kv_row(command, why)
                ui.separator()
                with ui.column().classes("w-full gap-3"):
                    with ui.row().classes("items-center gap-2"):
                        ui.badge("Dangerous if you do not mean it", color="negative")
                    for command, why in pnp_docs.DANGER_POINTS:
                        _manual_kv_row(command, why)
                    ui.label(
                        "There is no undo for delete/remove. Export first."
                    ).classes("text-body2 text-grey-8 mt-1")

        with ui.card().classes("w-full p-4 pnp-anchor") as switch_card:
            anchors["switches"] = switch_card
            with ui.expansion(
                "Full switch list (same as Command map)", icon="list"
            ).classes("w-full"):
                with ui.column().classes("w-full gap-4 p-2"):
                    ui.markdown(
                        "See the **Command map** tab for every switch, an example, "
                        "and whether this app already wraps it."
                    ).classes("pnp-manual-copy")
                    for group, cmds in pnp_docs.commands_by_group():
                        ui.label(group).classes("text-subtitle2 mt-2")
                        for cmd in cmds:
                            with ui.row().classes(
                                "w-full items-baseline gap-3 flex-wrap py-1"
                            ):
                                ui.code(cmd["switch"])
                                ui.label(cmd["title"]).classes("text-body2 font-bold")
                                ui.label(cmd["summary"]).classes(
                                    "text-body2 text-grey-8"
                                )

        with ui.card().classes("w-full p-6 mb-4 pnp-anchor") as compare_card:
            anchors["compare"] = compare_card
            with ui.column().classes("w-full gap-3"):
                ui.label("Not the same as…").classes("text-subtitle1 font-bold")
                for index, (name, how) in enumerate(pnp_docs.COMPARE_ITEMS):
                    if index:
                        ui.separator()
                    _manual_kv_row(name, how, mono_left=False)

        ui.button(
            icon="arrow_upward",
            on_click=make_jump("top"),
        ).props("round unelevated color=primary").classes(
            "fixed bottom-6 right-6 z-[3000] shadow-lg"
        ).tooltip("Back to top")


# ---------------------------------------------------------------------------
# Tab 3 — Command map
# ---------------------------------------------------------------------------


def build_command_map_tab() -> None:
    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-4"):
        with ui.card().classes("w-full"):
            ui.label("What pnputil can do").classes("text-h6")
            ui.markdown(pnp_docs.ROADMAP_MD)
            with ui.row().classes("gap-2 flex-wrap"):
                ui.badge("In this app", color="positive")
                ui.badge("UI later", color="grey")
                ui.badge("Destructive", color="negative")

        filter_box = (
            ui.input(placeholder="Filter switches…")
            .props("dense clearable debounce=200 outlined")
            .classes("w-full max-w-md")
        )

        cards_host = ui.column().classes("w-full gap-3")

        def render(query: str = "") -> None:
            cards_host.clear()
            q = (query or "").strip().lower()
            with cards_host:
                shown = 0
                for group, cmds in pnp_docs.commands_by_group():
                    filtered = [
                        c
                        for c in cmds
                        if not q
                        or q in c["switch"].lower()
                        or q in c["title"].lower()
                        or q in c["summary"].lower()
                        or q in c["group"].lower()
                    ]
                    if not filtered:
                        continue
                    ui.label(group).classes("text-subtitle1 font-bold mt-2")
                    for cmd in filtered:
                        shown += 1
                        danger = cmd["danger"]
                        with ui.card().classes("w-full"):
                            with ui.row().classes(
                                "w-full items-start justify-between gap-2 flex-wrap"
                            ):
                                with ui.column().classes("gap-0"):
                                    ui.label(cmd["title"]).classes(
                                        "text-subtitle1 font-bold"
                                    )
                                    ui.label(cmd["syntax"]).classes(
                                        "text-caption font-mono text-grey-8"
                                    )
                                with ui.row().classes("gap-1"):
                                    ui.badge(cmd["switch"], color="primary")
                                    ui.badge(
                                        pnp_docs.STATUS_LABEL[cmd["status"]],
                                        color=pnp_docs.STATUS_COLOR[cmd["status"]],
                                    )
                                    if danger:
                                        ui.badge("Destructive", color="negative")
                            ui.label(cmd["summary"]).classes("text-body2")
                            with ui.expansion("Details & examples", icon="code").classes(
                                "w-full"
                            ):
                                ui.markdown(cmd["details"])
                                for ex in cmd["examples"]:
                                    ui.code(ex).classes("w-full")
                                    ui.button(
                                        "Copy",
                                        icon="content_copy",
                                        on_click=lambda _e, example=ex: _copy(
                                            example
                                        ),
                                    ).props("flat dense")
                if shown == 0:
                    ui.label("No command matches that filter.").classes("text-grey-7")

        render()
        filter_box.on("update:model-value", lambda e: render(e.args or ""))


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


@ui.page("/")
def index() -> None:
    ui.colors(primary="#1565C0", secondary="#00897B", accent="#FF8F00")

    if not pnp_ops.is_windows():
        with ui.column().classes("w-full max-w-xl mx-auto p-8"):
            ui.label("Windows only").classes("text-h5")
            ui.label("`pnputil` exists only on Windows.")
        return

    with ui.header().classes("items-center justify-between px-4"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("developer_board", size="md")
            ui.label("Explorer Advance").classes("text-h6")
            ui.badge("PnPUtil").props("outline color=white")
        ui.label(f"Local only · http://127.0.0.1:{APP_PORT}").classes(
            "text-caption opacity-80"
        )

    with ui.tabs().classes("w-full px-2").props(
        "active-color=primary indicator-color=primary"
    ) as tabs:
        tab_drivers = ui.tab("drivers", label="Installed drivers", icon="search")
        tab_manual = ui.tab("manual", label="PnPUtil manual", icon="menu_book")
        tab_map = ui.tab("map", label="Command map", icon="map")

    with ui.tab_panels(tabs, value=tab_drivers).classes("w-full"):
        with ui.tab_panel(tab_drivers).classes("p-0"):
            build_drivers_tab()
        with ui.tab_panel(tab_manual).classes("p-0"):
            build_manual_tab()
        with ui.tab_panel(tab_map).classes("p-0"):
            build_command_map_tab()


def parse_server_args() -> argparse.Namespace:
    """Bind address: --host / --port, or PNPUTIL_HOST / PNPUTIL_PORT."""
    parser = argparse.ArgumentParser(description="Explorer Advance — PnPUtil UI")
    parser.add_argument(
        "--host",
        default=os.environ.get("PNPUTIL_HOST", "127.0.0.1"),
        help="Listen address (default: 127.0.0.1). Use 127.0.0.2 if another "
        "app or Chrome extension already owns localhost.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PNPUTIL_PORT", str(APP_PORT))),
        help=f"HTTP port (default: {APP_PORT}).",
    )
    args, _ = parser.parse_known_args()
    return args


def port_in_use(host: str, port: int) -> bool:
    probe = "127.0.0.1" if host in {"0.0.0.0", "::", ""} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((probe, port)) == 0


def pick_listen_port(host: str, preferred: int, *, span: int = 20) -> int:
    """Use `preferred` when free; otherwise the next free port in the span."""
    for port in range(preferred, preferred + span):
        if not port_in_use(host, port):
            return port
    return preferred


if __name__ in {"__main__", "__mp_main__"}:
    server = parse_server_args()
    port = pick_listen_port(server.host, server.port)
    if port != server.port:
        print(
            f"Port {server.port} is already in use "
            f"(another copy of this app is probably still running).\n"
            f"Starting on http://{server.host}:{port} instead.\n"
            f"To keep a chosen port: close the other window, or start with "
            f"`py -3 main.py --port {port + 1}`.",
            file=sys.stderr,
        )
    ui.run(
        title="Explorer Advance — PnPUtil",
        reload=False,
        host=server.host,
        port=port,
        show=True,
        favicon="🧩",
    )
