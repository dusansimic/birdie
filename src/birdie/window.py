"""Top-level application window: header, view switcher, toast overlay."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from birdie.async_utils import run_async
from birdie.views.events_view import EventsView
from birdie.views.networks_view import NetworksView
from birdie.views.profiles_view import ProfilesView
from birdie.views.status_view import StatusView


class BirdieWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.set_title("Birdie")
        self.set_default_size(920, 680)

        self.client = self.get_application().client
        self._bind_window_state()

        self._toast_overlay = Adw.ToastOverlay()
        self.set_content(self._toast_overlay)

        toolbar_view = Adw.ToolbarView()
        self._toast_overlay.set_child(toolbar_view)

        # -- view stack --------------------------------------------------
        self._stack = Adw.ViewStack()

        self.status_view = StatusView(self)
        self._stack.add_titled_with_icon(
            self.status_view, "status", "Status", "network-vpn-symbolic"
        )

        self.networks_view = NetworksView(self)
        self._stack.add_titled_with_icon(
            self.networks_view, "networks", "Networks",
            "network-workgroup-symbolic",
        )
        self.profiles_view = ProfilesView(self)
        self._stack.add_titled_with_icon(
            self.profiles_view, "profiles", "Profiles",
            "avatar-default-symbolic",
        )
        self.events_view = EventsView(self)
        self._stack.add_titled_with_icon(
            self.events_view, "events", "Events",
            "document-open-recent-symbolic",
        )

        # -- header ------------------------------------------------------
        header = Adw.HeaderBar()
        switcher = Adw.ViewSwitcher(
            stack=self._stack, policy=Adw.ViewSwitcherPolicy.WIDE
        )
        header.set_title_widget(switcher)
        header.pack_end(self._build_menu_button())
        toolbar_view.add_top_bar(header)

        toolbar_view.set_content(self._stack)

        # Bottom switcher for narrow widths.
        switcher_bar = Adw.ViewSwitcherBar(stack=self._stack)
        toolbar_view.add_bottom_bar(switcher_bar)
        self._stack.connect(
            "notify::visible-child",
            lambda *_: None,
        )
        switcher_bar.set_reveal(True)

        # Hide feature-gated pages once the daemon reports its feature flags.
        run_async(self.client.get_features(), on_success=self._apply_features,
                  on_error=lambda _e: None)

    def _apply_features(self, features) -> None:
        if features.disable_networks:
            page = self._stack.get_page(self.networks_view)
            if page is not None:
                page.set_visible(False)
        if features.disable_profiles:
            page = self._stack.get_page(self.profiles_view)
            if page is not None:
                page.set_visible(False)

    def _bind_window_state(self) -> None:
        # Persist geometry via GSettings, but only if the schema is actually
        # installed (a dev run from the source tree may not have it).
        source = Gio.SettingsSchemaSource.get_default()
        if source is None or source.lookup("org.birdie.Birdie", True) is None:
            return
        settings = Gio.Settings(schema_id="org.birdie.Birdie")
        settings.bind("window-width", self, "default-width",
                      Gio.SettingsBindFlags.DEFAULT)
        settings.bind("window-height", self, "default-height",
                      Gio.SettingsBindFlags.DEFAULT)
        settings.bind("window-maximized", self, "maximized",
                      Gio.SettingsBindFlags.DEFAULT)

    def _build_menu_button(self) -> Gtk.MenuButton:
        menu = Gio.Menu()
        menu.append("Preferences", "app.preferences")
        menu.append("About Birdie", "app.about")
        menu.append("Quit", "app.quit")
        button = Gtk.MenuButton(
            icon_name="open-menu-symbolic", menu_model=menu
        )
        return button

    # -- shared UI helpers --------------------------------------------------

    def toast(self, message: str, *, timeout: int = 3) -> None:
        self._toast_overlay.add_toast(Adw.Toast(title=message, timeout=timeout))
