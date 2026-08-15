"""FastAPI app with Slack routes and GitHub/Salesforce install HTTP."""

from fastapi import FastAPI

from app_integrations.github.router import router as github_app_router
from app_integrations.salesforce.router import router as salesforce_router
from slack_app.routes import router as slack_router

app = FastAPI(
    title="Aegra with Slack Integration",
    description="Aegra API server with Slack bot integration",
)

app.include_router(slack_router)
app.include_router(github_app_router)
app.include_router(salesforce_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check for the combined app."""
    return {"status": "healthy", "service": "aegra_slack_app"}
