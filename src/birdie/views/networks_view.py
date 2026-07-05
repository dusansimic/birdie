"""Networks view: list routed networks and toggle selection.

Selection maps to ``SelectNetworks``/``DeselectNetworks`` on individual network
IDs (with ``append=True`` so toggling one does not clobber the others). The
daemon only serves this list while connected, so a disconnected daemon shows a
friendly empty state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from birdie.async_utils import run_async
from birdie.daemon.client import DaemonError

if TYPE_CHECKING:
    from birdie.window import BirdieWindow


class NetworksView(Adw.Bin):
    def __init__(self, window: "BirdieWindow") -> None:
        super().__init__()
        self._window = window
        self._client = window.client
        self._rows: list[Gtk.Widget] = []
        self._suppress_toggle = False

        self._page = Adw.PreferencesPage()
        self._group = Adw.PreferencesGroup(
            title="Networks",
            description="Routed networks you can access through NetBird.",
        )
        self._page.add(self._group)

        self._empty = Adw.StatusPage(
            title="No networks",
            description="Connect to NetBird to see available networks.",
            icon_name="network-workgroup-symbolic",
        )

        self.set_child(self._empty)

        self.connect("map", lambda *_: self.refresh())

    def refresh(self) -> None:
        run_async(
            self._client.list_networks(),
            on_success=self._apply,
            on_error=self._on_error,
        )

    def _apply(self, resp) -> None:
        for row in self._rows:
            self._group.remove(row)
        self._rows.clear()

        networks = list(resp.routes)
        if not networks:
            self._empty.set_title("No networks")
            self._empty.set_description(
                "There are no routed networks for this profile."
            )
            self.set_child(self._empty)
            return

        self.set_child(self._page)
        for net in sorted(networks, key=lambda n: n.ID):
            row = Adw.SwitchRow(title=net.ID or net.range)
            subtitle = net.range
            if net.domains:
                subtitle = (
                    f"{subtitle}  ·  {', '.join(net.domains)}"
                    if subtitle
                    else ", ".join(net.domains)
                )
            row.set_subtitle(subtitle)
            self._suppress_toggle = True
            row.set_active(net.selected)
            self._suppress_toggle = False
            row.connect("notify::active", self._on_row_toggled, net.ID)
            self._group.add(row)
            self._rows.append(row)

    def _on_row_toggled(self, row: Adw.SwitchRow, _param, network_id: str) -> None:
        if self._suppress_toggle:
            return
        active = row.get_active()
        row.set_sensitive(False)

        def done(_result) -> None:
            row.set_sensitive(True)
            self._window.toast(f"{'Selected' if active else 'Deselected'} {network_id}")

        def failed(exc: BaseException) -> None:
            row.set_sensitive(True)
            # Revert the visual state on failure.
            self._suppress_toggle = True
            row.set_active(not active)
            self._suppress_toggle = False
            self._window.toast(f"Failed to update {network_id}: {exc}")

        if active:
            run_async(
                self._client.select_networks([network_id], append=True),
                on_success=done,
                on_error=failed,
            )
        else:
            run_async(
                self._client.deselect_networks([network_id]),
                on_success=done,
                on_error=failed,
            )

    def _on_error(self, exc: BaseException) -> None:
        # "not connected" is the common case when the tunnel is down.
        detail = str(exc)
        self._empty.set_title("Networks unavailable")
        self._empty.set_description(
            "Connect to NetBird to manage networks."
            if "not connected" in detail.lower()
            else detail
        )
        self.set_child(self._empty)
