"""FastAPI app with Slack routes and GitHub identity-linking for Aegra integration."""

from fastapi import FastAPI

from app_integrations.github.router import router as github_auth_router
from slack_app.routes import router as slack_router

# Create the FastAPI app
# This will be merged with Aegra's core routes
app = FastAPI(
    title="Aegra with Slack Integration",
    description="Aegra API server with Slack bot integration and GitHub identity linking",
)

# Include Slack event/command routes
app.include_router(slack_router)

# Include GitHub OAuth identity-linking routes (/auth/github/start, /auth/github/callback)
app.include_router(github_auth_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check for the combined app."""
    return {"status": "healthy", "service": "aegra_slack_app"}
