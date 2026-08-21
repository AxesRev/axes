"""Lambda async helper keeps one event loop across warm invokes."""

from __future__ import annotations

import asyncio

import pytest

from common.lambda_async import run


@pytest.mark.unit
def test_run_reuses_the_same_event_loop() -> None:
    loops: list[asyncio.AbstractEventLoop] = []

    async def record_loop() -> int:
        loops.append(asyncio.get_running_loop())
        return 1

    assert run(record_loop()) == 1
    assert run(record_loop()) == 1
    assert loops[0] is loops[1]
