"""Login dialog: interactive SSO device flow or setup-key authentication.

SSO flow mirrors the CLI:
  Login  → (needsSSOLogin) open verificationURIComplete in a browser
         → WaitSSOLogin  (blocks until the user finishes)
         → Up

Setup-key flow skips the browser step: Login(setupKey) → Up.
"""

from __future__ import annotations

import asyncio
import socket
from typing import TYPE_CHECKING, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from birdie.async_utils import run_async
from birdie.daemon.client import DaemonError

if TYPE_CHECKING:
    from birdie.window import BirdieWindow


class LoginDialog(Adw.Dialog):
    def __init__(self, window: "BirdieWindow") -> None:
        super().__init__()
        self._window = window
        self._client = window.client
        self._task: Optional[asyncio.Task] = None

        self.set_title("Log In to NetBird")
        self.set_content_width(420)

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)
        self.set_child(toolbar_view)

        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        toolbar_view.set_content(self._stack)

        self._stack.add_named(self._build_chooser(), "chooser")
        self._stack.add_named(self._build_setupkey(), "setupkey")
        self._stack.add_named(self._build_progress(), "progress")
        self._stack.set_visible_child_name("chooser")

    # -- pages -------------------------------------------------------------

    def _build_chooser(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            description="Choose how to authenticate this device."
        )
        page.add(group)

        sso_row = Adw.ActionRow(
            title="Single Sign-On",
            subtitle="Authenticate in your web browser.",
            activatable=True,
        )
        sso_row.add_prefix(Gtk.Image.new_from_icon_name("web-browser-symbolic"))
        sso_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        sso_row.connect("activated", lambda *_: self._start_sso())
        group.add(sso_row)

        key_row = Adw.ActionRow(
            title="Setup Key",
            subtitle="Use a pre-authorized setup key.",
            activatable=True,
        )
        key_row.add_prefix(Gtk.Image.new_from_icon_name("dialog-password-symbolic"))
        key_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        key_row.connect(
            "activated", lambda *_: self._stack.set_visible_child_name("setupkey")
        )
        group.add(key_row)
        return page

    def _build_setupkey(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Setup Key")
        page.add(group)

        self._key_entry = Adw.PasswordEntryRow(title="Setup key")
        group.add(self._key_entry)

        button_group = Adw.PreferencesGroup()
        page.add(button_group)
        submit = Gtk.Button(label="Connect", halign=Gtk.Align.CENTER)
        submit.add_css_class("suggested-action")
        submit.add_css_class("pill")
        submit.connect("clicked", lambda *_: self._start_setupkey())
        button_group.add(submit)
        return page

    def _build_progress(self) -> Gtk.Widget:
        self._status_page = Adw.StatusPage(
            title="Waiting for authentication",
            description="Complete the login in your browser.",
        )
        spinner = Adw.Spinner(width_request=48, height_request=48)
        self._status_page.set_child(self._build_progress_box(spinner))
        return self._status_page

    def _build_progress_box(self, spinner: Gtk.Widget) -> Gtk.Widget:
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            halign=Gtk.Align.CENTER,
        )
        box.append(spinner)

        self._code_label = Gtk.Label()
        self._code_label.add_css_class("title-1")
        self._code_label.set_selectable(True)
        box.append(self._code_label)

        self._open_button = Gtk.Button(label="Open Browser Again")
        self._open_button.add_css_class("pill")
        self._open_button.set_halign(Gtk.Align.CENTER)
        self._open_button.set_visible(False)
        box.append(self._open_button)
        return box

    # -- SSO flow ----------------------------------------------------------

    def _start_sso(self) -> None:
        self._stack.set_visible_child_name("progress")
        self._status_page.set_title("Contacting management server…")
        self._code_label.set_text("")
        self._task = run_async(self._run_sso(), on_error=self._on_flow_error)

    async def _run_sso(self) -> None:
        hostname = socket.gethostname()
        resp = await self._client.login(hostname=hostname)
        if not resp.needsSSOLogin:
            # Already authorized (cached token) — just bring it up.
            await self._client.up()
            self._finish("Connecting…")
            return

        url = resp.verificationURIComplete or resp.verificationURI
        self._status_page.set_title("Waiting for authentication")
        self._status_page.set_description(
            "A browser window should open. If it did not, use the code below."
        )
        if resp.userCode:
            self._code_label.set_text(resp.userCode)
        self._open_url(url)
        self._open_button.set_visible(True)
        self._open_button.connect("clicked", lambda *_: self._open_url(url))

        await self._client.wait_sso_login(resp.userCode, hostname)
        await self._client.up()
        self._finish("Connecting…")

    # -- setup-key flow ----------------------------------------------------

    def _start_setupkey(self) -> None:
        key = self._key_entry.get_text().strip()
        if not key:
            self._window.toast("Enter a setup key.")
            return
        self._stack.set_visible_child_name("progress")
        self._status_page.set_title("Authenticating…")
        self._open_button.set_visible(False)
        self._task = run_async(self._run_setupkey(key), on_error=self._on_flow_error)

    async def _run_setupkey(self, key: str) -> None:
        await self._client.login(setup_key=key, hostname=socket.gethostname())
        await self._client.up()
        self._finish("Connecting…")

    # -- helpers -----------------------------------------------------------

    def _open_url(self, url: str) -> None:
        if not url:
            return
        launcher = Gtk.UriLauncher.new(url)
        launcher.launch(self._window, None, None)

    def _finish(self, message: str) -> None:
        self._window.toast(message)
        self._window.status_view.refresh()
        self.close()

    def _on_flow_error(self, exc: BaseException) -> None:
        if isinstance(exc, DaemonError):
            self._window.toast(f"Login failed: {exc}")
        else:
            self._window.toast(f"Login error: {exc}")
        self.close()

    def do_closed(self) -> None:  # noqa: N802 - GObject vfunc
        if self._task is not None and not self._task.done():
            self._task.cancel()
