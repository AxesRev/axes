"""FastAPI app with Slack event routes."""

from fastapi import FastAPI

from slack_app.routes import router as slack_router

app = FastAPI(
    title="Aegra with Slack Integration",
    description="Aegra API server with Slack bot integration",
)

app.include_router(slack_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check for the combined app."""
    return {"status": "healthy", "service": "aegra_slack_app"}
