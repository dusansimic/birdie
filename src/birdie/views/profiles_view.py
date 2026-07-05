"""Profiles view: list, switch, add, rename, and remove connection profiles.

Profiles are per-OS-user; every RPC carries the current login name. Hidden
entirely when ``GetFeatures.disable_profiles`` is set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from birdie.async_utils import run_async

if TYPE_CHECKING:
    from birdie.window import BirdieWindow


class ProfilesView(Adw.Bin):
    def __init__(self, window: "BirdieWindow") -> None:
        super().__init__()
        self._window = window
        self._client = window.client
        self._rows: list[Gtk.Widget] = []

        self._page = Adw.PreferencesPage()
        self._group = Adw.PreferencesGroup(
            title="Profiles",
            description="Switching profiles changes which NetBird account this "
                        "device uses.",
        )
        self._page.add(self._group)
        self.set_child(self._page)

        self.connect("map", lambda *_: self.refresh())

    def refresh(self) -> None:
        run_async(self._client.list_profiles(),
                  on_success=self._apply,
                  on_error=lambda e: self._window.toast(f"Profiles: {e}"))

    def _apply(self, resp) -> None:
        for row in self._rows:
            self._group.remove(row)
        self._rows.clear()

        for prof in resp.profiles:
            row = Adw.ActionRow(title=prof.name)
            if prof.is_active:
                row.set_subtitle("Active")
                check = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                check.add_css_class("accent")
                row.add_prefix(check)
            else:
                row.set_activatable(True)
                row.connect("activated", self._on_switch, prof.name)

            menu = self._row_menu(prof.name, prof.is_active)
            row.add_suffix(menu)
            self._group.add(row)
            self._rows.append(row)

    def _row_menu(self, name: str, is_active: bool) -> Gtk.Widget:
        box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        if not is_active:
            switch_btn = Gtk.Button(label="Use", valign=Gtk.Align.CENTER)
            switch_btn.add_css_class("flat")
            switch_btn.connect("clicked", lambda *_: self._do_switch(name))
            box.append(switch_btn)

        rename_btn = Gtk.Button(icon_name="document-edit-symbolic",
                                valign=Gtk.Align.CENTER)
        rename_btn.add_css_class("flat")
        rename_btn.set_tooltip_text("Rename")
        rename_btn.connect("clicked", lambda *_: self._prompt_rename(name))
        box.append(rename_btn)

        remove_btn = Gtk.Button(icon_name="user-trash-symbolic",
                                valign=Gtk.Align.CENTER)
        remove_btn.add_css_class("flat")
        remove_btn.set_tooltip_text("Remove")
        remove_btn.set_sensitive(not is_active)
        remove_btn.connect("clicked", lambda *_: self._confirm_remove(name))
        box.append(remove_btn)
        return box

    # -- actions -----------------------------------------------------------

    def _on_switch(self, _row, name: str) -> None:
        self._do_switch(name)

    def _do_switch(self, name: str) -> None:
        run_async(self._client.switch_profile(name),
                  on_success=lambda _: self._after(f"Switched to {name}"),
                  on_error=lambda e: self._window.toast(f"Switch failed: {e}"))

    def add_profile_dialog(self) -> None:
        """Prompt for a new profile name and add it.

        Public entry point for the Add action, which now lives in the window
        header bar rather than a per-view header.
        """
        self._prompt_add()

    def _prompt_add(self) -> None:
        self._name_dialog("Add Profile", "", lambda text: run_async(
            self._client.add_profile(text),
            on_success=lambda _: self._after(f"Added {text}"),
            on_error=lambda e: self._window.toast(f"Add failed: {e}")))

    def _prompt_rename(self, old: str) -> None:
        self._name_dialog("Rename Profile", old, lambda text: run_async(
            self._client.rename_profile(old, text),
            on_success=lambda _: self._after(f"Renamed to {text}"),
            on_error=lambda e: self._window.toast(f"Rename failed: {e}")))

    def _confirm_remove(self, name: str) -> None:
        dialog = Adw.AlertDialog(
            heading="Remove profile?",
            body=f"“{name}” will be permanently removed.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Remove")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")

        def on_response(_d, response: str) -> None:
            if response == "remove":
                run_async(self._client.remove_profile(name),
                          on_success=lambda _: self._after(f"Removed {name}"),
                          on_error=lambda e: self._window.toast(f"Remove failed: {e}"))

        dialog.connect("response", on_response)
        dialog.present(self._window)

    def _name_dialog(self, heading: str, initial: str, on_ok) -> None:
        dialog = Adw.AlertDialog(heading=heading)
        entry = Gtk.Entry(text=initial, activates_default=True)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "Save")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("ok")

        def on_response(_d, response: str) -> None:
            if response == "ok":
                text = entry.get_text().strip()
                if text:
                    on_ok(text)

        dialog.connect("response", on_response)
        dialog.present(self._window)

    def _after(self, message: str) -> None:
        self._window.toast(message)
        self.refresh()
        self._window.status_view.refresh()
