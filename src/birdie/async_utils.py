"""Helpers for driving async daemon calls from GTK widgets.

Birdie installs :class:`gi.events.GLibEventLoopPolicy` (PyGObject >= 3.50),
which makes the GLib main loop *be* the asyncio event loop. That means we can
schedule coroutines with ``asyncio`` and they run cooperatively alongside GTK
without threads or ``GLib.idle_add`` marshalling.
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")


def run_async(
    coro: Awaitable[T],
    *,
    on_error: Optional[Callable[[BaseException], None]] = None,
    on_success: Optional[Callable[[T], None]] = None,
) -> "asyncio.Task[T]":
    """Schedule *coro* on the running GLib/asyncio loop.

    ``on_success`` / ``on_error`` are invoked on the same loop when the task
    finishes. Cancellation is swallowed silently.
    """

    async def _wrapper() -> Optional[T]:
        try:
            result = await coro
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # noqa: BLE001 - surfaced via on_error
            if on_error is not None:
                on_error(exc)
            else:
                traceback.print_exc()
            return None
        if on_success is not None:
            on_success(result)
        return result

    return asyncio.ensure_future(_wrapper())
