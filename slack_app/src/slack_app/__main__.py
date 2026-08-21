"""Run the Slack app with HOST/PORT from SlackSettings."""

import uvicorn

from slack_app.config import slack_settings


def main() -> None:
    uvicorn.run("slack_app.app:app", host=slack_settings.HOST, port=slack_settings.PORT)


if __name__ == "__main__":
    main()
