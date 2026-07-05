"""The Adwaita application object: actions, lifecycle, shared daemon client."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk  # noqa: E402

from birdie import __version__
from birdie.daemon.client import NetbirdClient
from birdie.window import BirdieWindow

APP_ID = "me.dusansimic.Birdie"


class BirdieApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.client = NetbirdClient()
        self._window: BirdieWindow | None = None

        self._add_action("about", self._on_about)
        self._add_action("preferences", self._on_preferences, accels=["<primary>comma"])
        self._add_action("quit", lambda *_: self.quit(), accels=["<primary>q"])

    def _add_action(self, name: str, callback, accels: list[str] | None = None) -> None:
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if accels:
            self.set_accels_for_action(f"app.{name}", accels)

    def do_activate(self) -> None:  # noqa: N802 - GObject vfunc
        if self._window is None:
            self._window = BirdieWindow(application=self)
        self._window.present()

    def _on_preferences(self, *_args) -> None:
        from birdie.preferences import PreferencesDialog

        dialog = PreferencesDialog(self._window)
        dialog.present(self._window)

    def _on_about(self, *_args) -> None:
        about = Adw.AboutDialog(
            application_name="Birdie",
            application_icon=APP_ID,
            developer_name="Birdie contributors",
            version=__version__,
            comments="A GNOME front-end for the NetBird client.",
            website="https://github.com/netbirdio/netbird",
            license_type=Gtk.License.GPL_3_0,
        )
        about.present(self._window)
