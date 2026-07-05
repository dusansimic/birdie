"""Application entry point.

Installs the GLib-backed asyncio event loop policy *before* any event loop is
created, then hands control to the Adwaita application. Startup must go through
``Gtk.Application.run`` (not ``asyncio.run``), which spins the GLib main loop
that our asyncio tasks piggy-back on.
"""

from __future__ import annotations

import asyncio
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.events import GLibEventLoopPolicy  # noqa: E402


def main() -> int:
    # Must be set before the first event loop is created.
    asyncio.set_event_loop_policy(GLibEventLoopPolicy())

    from birdie.application import BirdieApplication

    app = BirdieApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
