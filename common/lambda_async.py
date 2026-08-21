"""Run async Lambda handlers on one event loop per container.

``asyncio.run()`` creates a loop, closes it when the handler returns, then the
next warm invoke gets a new loop. SQLAlchemy/asyncpg connections from the first
call stay bound to the dead loop and the second call 500s.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine

_loop: asyncio.AbstractEventLoop | None = None


def run[T](coro: Coroutine[object, object, T]) -> T:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)
