"""Preferences dialog backed by the daemon's ``GetConfig``/``SetConfig``.

Each toggle applies immediately, sending a ``SetConfigRequest`` that carries
only the single changed (optional) field so the daemon leaves everything else
untouched. Fields locked by an MDM policy (reported in ``mDMManagedFields``)
render read-only; if the daemon still rejects a change with
``FailedPrecondition`` the toggle is reverted and a toast explains why.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

import grpc  # noqa: E402
from gi.repository import Adw  # noqa: E402

from birdie.async_utils import run_async
from birdie.daemon.client import DaemonError, current_username
from birdie.daemon import daemon_pb2 as pb

if TYPE_CHECKING:
    from birdie.window import BirdieWindow

# (proto field on SetConfigRequest, GetConfigResponse attr, title, subtitle,
#  best-effort MDM key name). Booleans only.
BOOL_FIELDS = [
    ("disableAutoConnect", "disableAutoConnect", "Disable auto-connect",
     "Do not connect automatically when the daemon starts.", "disableAutoConnect"),
    ("rosenpassEnabled", "rosenpassEnabled", "Rosenpass (post-quantum)",
     "Enable post-quantum key exchange.", "rosenpassEnabled"),
    ("serverSSHAllowed", "serverSSHAllowed", "Allow SSH server",
     "Permit incoming NetBird SSH connections.", "serverSSHAllowed"),
    ("networkMonitor", "networkMonitor", "Network monitor",
     "Restart the connection on network changes.", "networkMonitor"),
    ("lazyConnectionEnabled", "lazyConnectionEnabled", "Lazy connections",
     "Establish peer connections on demand.", "lazyConnectionEnabled"),
    ("disable_notifications", "disable_notifications", "Disable notifications",
     "Suppress desktop notifications from the daemon.", "disableNotifications"),
    ("disable_dns", "disable_dns", "Disable DNS",
     "Do not manage DNS settings.", "disableDNS"),
    ("disable_client_routes", "disable_client_routes", "Disable client routes",
     "Do not apply routes received from the network.", "disableClientRoutes"),
    ("disable_server_routes", "disable_server_routes", "Disable server routes",
     "Do not advertise routes to other peers.", "disableServerRoutes"),
    ("block_lan_access", "block_lan_access", "Block LAN access",
     "Prevent peers from reaching your local network.", "blockLANAccess"),
    ("block_inbound", "blockInbound", "Block inbound",
     "Drop all inbound connections from peers.", "blockInbound"),
    ("disable_ipv6", "disable_ipv6", "Disable IPv6",
     "Turn off IPv6 within the tunnel.", "disableIPv6"),
]


class PreferencesDialog(Adw.PreferencesDialog):
    def __init__(self, window: "BirdieWindow") -> None:
        super().__init__()
        self._window = window
        self._client = window.client
        self._profile_name = ""
        self._managed: set[str] = set()
        self._suppress = False
        self._rows: dict[str, Adw.SwitchRow] = {}

        self.set_title("Preferences")

        page = Adw.PreferencesPage(title="General", icon_name="emblem-system-symbolic")
        self.add(page)

        self._info_group = Adw.PreferencesGroup(title="Connection")
        page.add(self._info_group)
        self._mgmt_row = Adw.ActionRow(title="Management URL", subtitle="—")
        self._iface_row = Adw.ActionRow(title="Interface", subtitle="—")
        self._port_row = Adw.ActionRow(title="WireGuard port", subtitle="—")
        self._mtu_row = Adw.ActionRow(title="MTU", subtitle="—")
        for row in (self._mgmt_row, self._iface_row, self._port_row, self._mtu_row):
            row.add_css_class("property")
            self._info_group.add(row)

        self._toggle_group = Adw.PreferencesGroup(title="Behaviour")
        page.add(self._toggle_group)
        for proto_field, _attr, title, subtitle, _key in BOOL_FIELDS:
            row = Adw.SwitchRow(title=title, subtitle=subtitle)
            row.connect("notify::active", self._on_toggle, proto_field)
            self._toggle_group.add(row)
            self._rows[proto_field] = row

        run_async(self._load(), on_error=lambda e: self._window.toast(f"Config: {e}"))

    async def _load(self) -> None:
        active = await self._client.get_active_profile()
        self._profile_name = active.profileName
        cfg = await self._client.get_config()
        self._managed = set(cfg.mDMManagedFields)
        self._apply_config(cfg)

    def _apply_config(self, cfg) -> None:
        self._suppress = True
        self._mgmt_row.set_subtitle(cfg.managementUrl or "—")
        self._iface_row.set_subtitle(cfg.interfaceName or "—")
        self._port_row.set_subtitle(str(cfg.wireguardPort) if cfg.wireguardPort else "—")
        self._mtu_row.set_subtitle(str(cfg.mtu) if cfg.mtu else "—")

        for proto_field, attr, _title, subtitle, mdm_key in BOOL_FIELDS:
            row = self._rows[proto_field]
            row.set_active(bool(getattr(cfg, attr)))
            if mdm_key in self._managed:
                row.set_sensitive(False)
                row.set_subtitle(f"{subtitle}  ·  Managed by MDM")
        self._suppress = False

    def _on_toggle(self, row: Adw.SwitchRow, _param, proto_field: str) -> None:
        if self._suppress:
            return
        value = row.get_active()
        row.set_sensitive(False)

        req = pb.SetConfigRequest(
            username=current_username(),
            profileName=self._profile_name,
        )
        setattr(req, proto_field, value)

        def done(_result) -> None:
            row.set_sensitive(True)

        def failed(exc: BaseException) -> None:
            self._suppress = True
            row.set_active(not value)
            self._suppress = False
            code = getattr(exc, "code", None)
            if code == grpc.StatusCode.FAILED_PRECONDITION:
                row.set_sensitive(False)
                self._window.toast("This setting is managed by MDM.")
            else:
                row.set_sensitive(True)
                self._window.toast(f"Could not save: {exc}")

        run_async(self._client.set_config(req), on_success=done, on_error=failed)
