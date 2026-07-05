"""Events & diagnostics view.

Shows the daemon's live event stream (``SubscribeEvents``) and exposes the
common admin actions: log-level selection (``Get/SetLogLevel``) and generating
an anonymized debug bundle (``DebugBundle``).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from birdie.async_utils import run_async
from birdie.daemon import daemon_pb2 as pb

if TYPE_CHECKING:
    from birdie.window import BirdieWindow

LOG_LEVELS = ["PANIC", "FATAL", "ERROR", "WARN", "INFO", "DEBUG", "TRACE"]

_SEVERITY_ICON = {
    pb.SystemEvent.Severity.INFO: "emblem-default-symbolic",
    pb.SystemEvent.Severity.WARNING: "dialog-warning-symbolic",
    pb.SystemEvent.Severity.ERROR: "dialog-error-symbolic",
    pb.SystemEvent.Severity.CRITICAL: "dialog-error-symbolic",
}


class EventsView(Adw.Bin):
    def __init__(self, window: "BirdieWindow") -> None:
        super().__init__()
        self._window = window
        self._client = window.client
        self._sub_task: Optional[asyncio.Task] = None
        self._event_rows: list[Gtk.Widget] = []

        page = Adw.PreferencesPage()
        self.set_child(page)

        # -- diagnostics controls ---------------------------------------
        diag = Adw.PreferencesGroup(title="Diagnostics")
        page.add(diag)

        self._loglevel_row = Adw.ComboRow(
            title="Log level",
            model=Gtk.StringList.new(LOG_LEVELS),
        )
        self._loglevel_row.connect("notify::selected", self._on_loglevel_changed)
        self._suppress_level = False
        diag.add(self._loglevel_row)

        bundle_row = Adw.ActionRow(
            title="Debug bundle",
            subtitle="Generate an anonymized diagnostics archive.",
            activatable=True,
        )
        bundle_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        bundle_row.connect("activated", lambda *_: self._make_bundle())
        diag.add(bundle_row)

        # -- events ------------------------------------------------------
        self._events_group = Adw.PreferencesGroup(
            title="Events", description="Live events from the NetBird daemon."
        )
        page.add(self._events_group)
        self._events_placeholder = Adw.ActionRow(
            title="No events yet", subtitle="Events appear here as they occur."
        )
        self._events_group.add(self._events_placeholder)

        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)

    # -- lifecycle ---------------------------------------------------------

    def _on_map(self, *_args) -> None:
        run_async(self._load_level(),
                  on_error=lambda e: self._window.toast(f"Log level: {e}"))
        if self._sub_task is None or self._sub_task.done():
            self._sub_task = run_async(self._consume_events(),
                                       on_error=self._on_stream_error)

    def _on_unmap(self, *_args) -> None:
        if self._sub_task is not None and not self._sub_task.done():
            self._sub_task.cancel()
            self._sub_task = None

    async def _load_level(self) -> None:
        resp = await self._client.get_log_level()
        name = pb.LogLevel.Name(resp.level)
        if name in LOG_LEVELS:
            self._suppress_level = True
            self._loglevel_row.set_selected(LOG_LEVELS.index(name))
            self._suppress_level = False

    # -- events stream -----------------------------------------------------

    async def _consume_events(self) -> None:
        async for event in self._client.subscribe_events():
            self._add_event(event)

    def _add_event(self, event) -> None:
        self._events_placeholder.set_visible(False)
        icon_name = _SEVERITY_ICON.get(event.severity, "emblem-default-symbolic")
        category = pb.SystemEvent.Category.Name(event.category)
        row = Adw.ActionRow(
            title=event.userMessage or event.message,
            subtitle=f"{category} · {event.message}" if event.userMessage else category,
        )
        row.add_prefix(Gtk.Image.new_from_icon_name(icon_name))
        self._events_group.add(row)
        # Newest on top, capped at 100 rows.
        self._events_group.remove(row)
        self._events_group.add(row)
        self._event_rows.insert(0, row)
        if len(self._event_rows) > 100:
            old = self._event_rows.pop()
            self._events_group.remove(old)

    def _on_stream_error(self, exc: BaseException) -> None:
        self._events_placeholder.set_visible(True)
        self._events_placeholder.set_subtitle(f"Event stream unavailable: {exc}")

    # -- diagnostics actions ----------------------------------------------

    def _on_loglevel_changed(self, row: Adw.ComboRow, _param) -> None:
        if self._suppress_level:
            return
        name = LOG_LEVELS[row.get_selected()]
        level = pb.LogLevel.Value(name)
        run_async(self._client.set_log_level(level),
                  on_success=lambda _: self._window.toast(f"Log level set to {name}"),
                  on_error=lambda e: self._window.toast(f"Failed: {e}"))

    def _make_bundle(self) -> None:
        self._window.toast("Generating debug bundle…")
        run_async(self._client.debug_bundle(anonymize=True, system_info=True),
                  on_success=self._bundle_done,
                  on_error=lambda e: self._window.toast(f"Bundle failed: {e}"))

    def _bundle_done(self, resp) -> None:
        dialog = Adw.AlertDialog(
            heading="Debug bundle created",
            body=f"Saved to:\n{resp.path}",
        )
        dialog.add_response("ok", "OK")
        dialog.present(self._window)
