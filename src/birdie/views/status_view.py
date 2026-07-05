"""Status dashboard: connection state, local peer, and peer list.

Polls ``Status`` on a timer while the view is on screen and renders the
``FullStatus`` snapshot. The connect/disconnect control maps to ``Up``/``Down``.
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

POLL_INTERVAL_SECONDS = 2


class StatusView(Adw.Bin):
    def __init__(self, window: "BirdieWindow") -> None:
        super().__init__()
        self._window = window
        self._client = window.client
        self._poll_source: Optional[int] = None
        self._busy = False
        self._connected = False
        self._needs_login = False

        page = Adw.PreferencesPage()
        self.set_child(page)

        # -- connection group -------------------------------------------
        conn_group = Adw.PreferencesGroup()
        page.add(conn_group)

        self._conn_row = Adw.ActionRow(
            title="Disconnected", subtitle="Checking daemon…"
        )
        self._conn_icon = Gtk.Image.new_from_icon_name("network-offline-symbolic")
        self._conn_row.add_prefix(self._conn_icon)

        self._connect_button = Gtk.Button(valign=Gtk.Align.CENTER)
        self._connect_button.add_css_class("suggested-action")
        self._connect_button.connect("clicked", self._on_toggle_clicked)
        self._conn_row.add_suffix(self._connect_button)
        conn_group.add(self._conn_row)

        # -- this device -------------------------------------------------
        self._device_group = Adw.PreferencesGroup(title="This device")
        page.add(self._device_group)
        self._ip_row = Adw.ActionRow(title="NetBird IP", subtitle="—")
        self._ip_row.add_css_class("property")
        self._fqdn_row = Adw.ActionRow(title="Domain", subtitle="—")
        self._fqdn_row.add_css_class("property")
        self._mgmt_row = Adw.ActionRow(title="Management", subtitle="—")
        self._mgmt_row.add_css_class("property")
        self._version_row = Adw.ActionRow(title="Daemon version", subtitle="—")
        self._version_row.add_css_class("property")
        for row in (self._ip_row, self._fqdn_row, self._mgmt_row, self._version_row):
            self._device_group.add(row)

        # -- peers -------------------------------------------------------
        self._peers_group = Adw.PreferencesGroup(title="Peers")
        page.add(self._peers_group)
        self._peer_rows: list[Gtk.Widget] = []
        self._peers_placeholder = Adw.ActionRow(
            title="No peers", subtitle="Connect to see network peers."
        )
        self._peers_group.add(self._peers_placeholder)

        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)

    # -- polling lifecycle -------------------------------------------------

    def _on_map(self, *_args) -> None:
        self.refresh()
        if self._poll_source is None:
            self._poll_source = GLib.timeout_add_seconds(
                POLL_INTERVAL_SECONDS, self._on_poll_tick
            )

    def _on_unmap(self, *_args) -> None:
        if self._poll_source is not None:
            GLib.source_remove(self._poll_source)
            self._poll_source = None

    def _on_poll_tick(self) -> bool:
        if not self._busy:
            self.refresh()
        return GLib.SOURCE_CONTINUE

    def refresh(self) -> None:
        run_async(self._client.status(full=True, probes=False),
                  on_success=self._apply_status,
                  on_error=self._on_status_error)

    # -- rendering ---------------------------------------------------------

    def _apply_status(self, status) -> None:
        state = status.status  # e.g. "Connected", "Connecting", "NeedsLogin", "Disconnected"
        self._connected = state == "Connected"
        needs_login = state == "NeedsLogin"
        self._needs_login = needs_login

        self._version_row.set_subtitle(status.daemonVersion or "—")

        if self._connected:
            self._conn_row.set_title("Connected")
            self._conn_icon.set_from_icon_name("network-vpn-symbolic")
        elif state == "Connecting":
            self._conn_row.set_title("Connecting…")
            self._conn_icon.set_from_icon_name("network-vpn-acquiring-symbolic")
        elif needs_login:
            self._conn_row.set_title("Login required")
            self._conn_icon.set_from_icon_name("network-offline-symbolic")
        else:
            self._conn_row.set_title("Disconnected")
            self._conn_icon.set_from_icon_name("network-offline-symbolic")

        fs = status.fullStatus
        mgmt = fs.managementState
        self._conn_row.set_subtitle(mgmt.URL or "")
        self._mgmt_row.set_subtitle(
            f"{'Connected' if mgmt.connected else 'Disconnected'} · {mgmt.URL}"
            if mgmt.URL else "—"
        )
        local = fs.localPeerState
        self._ip_row.set_subtitle(local.IP or "—")
        self._fqdn_row.set_subtitle(local.fqdn or "—")

        self._render_peers(fs.peers)

        if self._connected:
            self._connect_button.set_label("Disconnect")
            self._connect_button.remove_css_class("suggested-action")
            self._connect_button.add_css_class("destructive-action")
        else:
            self._connect_button.set_label(
                "Log In & Connect" if needs_login else "Connect"
            )
            self._connect_button.remove_css_class("destructive-action")
            self._connect_button.add_css_class("suggested-action")
        self._connect_button.set_sensitive(not self._busy and state != "Connecting")

    def _render_peers(self, peers) -> None:
        for row in self._peer_rows:
            self._peers_group.remove(row)
        self._peer_rows.clear()

        if not peers:
            self._peers_placeholder.set_visible(True)
            return
        self._peers_placeholder.set_visible(False)

        for peer in peers:
            connected = peer.connStatus == "Connected"
            transport = "relayed" if peer.relayed else "direct"
            subtitle_parts = [peer.IP]
            if connected:
                subtitle_parts.append(transport)
                if peer.latency and peer.latency.ToMilliseconds() > 0:
                    subtitle_parts.append(f"{peer.latency.ToMilliseconds()} ms")
            row = Adw.ActionRow(
                title=peer.fqdn or peer.IP,
                subtitle=" · ".join(p for p in subtitle_parts if p),
            )
            icon = Gtk.Image.new_from_icon_name(
                "network-transmit-receive-symbolic" if connected
                else "network-offline-symbolic"
            )
            row.add_prefix(icon)
            badge = Gtk.Label(label=peer.connStatus)
            badge.add_css_class("dim-label")
            badge.set_valign(Gtk.Align.CENTER)
            row.add_suffix(badge)
            self._peers_group.add(row)
            self._peer_rows.append(row)

    def _on_status_error(self, exc: BaseException) -> None:
        message = str(exc)
        self._conn_row.set_title("Daemon unavailable")
        self._conn_row.set_subtitle(message)
        self._conn_icon.set_from_icon_name("dialog-warning-symbolic")
        self._connect_button.set_sensitive(False)

    # -- actions -----------------------------------------------------------

    def _on_toggle_clicked(self, _button) -> None:
        if self._busy:
            return
        if self._connected:
            self._busy = True
            self._connect_button.set_sensitive(False)
            run_async(self._client.down(),
                      on_success=lambda _: self._after_action("Disconnected"),
                      on_error=self._on_action_error)
        elif self._needs_login:
            self._open_login()
        else:
            self._busy = True
            self._connect_button.set_sensitive(False)
            run_async(self._client.up(),
                      on_success=lambda _: self._after_action("Connecting…"),
                      on_error=self._on_action_error)

    def _open_login(self) -> None:
        from birdie.views.login_dialog import LoginDialog

        dialog = LoginDialog(self._window)
        dialog.present(self._window)

    def _after_action(self, message: str) -> None:
        self._busy = False
        self._window.toast(message)
        self.refresh()

    def _on_action_error(self, exc: BaseException) -> None:
        self._busy = False
        self._connect_button.set_sensitive(True)
        if isinstance(exc, DaemonError):
            self._window.toast(f"Action failed: {exc}")
        else:
            self._window.toast(f"Unexpected error: {exc}")
        self.refresh()
