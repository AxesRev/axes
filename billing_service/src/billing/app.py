"""Billing FastAPI app. Served by uvicorn locally and Mangum on Lambda."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aegra_api.core.database import db_manager
from fastapi import FastAPI
from mangum import Mangum

from billing.routes import router as billing_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await db_manager.initialize_metadata()
    try:
        yield
    finally:
        await db_manager.close()


app = FastAPI(
    title="Axes billing",
    description="Paddle billing status, customer portal, and webhooks",
    lifespan=lifespan,
)
app.include_router(billing_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "billing"}


handler = Mangum(app, lifespan="auto")
