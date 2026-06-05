"""Monthly token usage billing cron job.

Run from the repo root on a schedule, e.g. the 1st of each month:

    uv run python -m slack_app.charge_usage
"""

from __future__ import annotations

import asyncio
import json
import sys

import structlog
from sqlalchemy.exc import SQLAlchemyError

from aegra_api.core.database import db_manager
from aegra_api.core.orm import get_metadata_session_maker
from slack_app.billing_service import charge_monthly_usage_for_all_tenants, current_month_period
from slack_app.config import billing_settings

logger = structlog.getLogger(__name__)


def _validate_config() -> str | None:
    if not billing_settings.PADDLE_API_KEY.strip():
        return "PADDLE_API_KEY is not configured"
    if not billing_settings.PADDLE_USAGE_PRICE_ID.strip():
        return "PADDLE_USAGE_PRICE_ID is not configured"
    return None


async def _async_main() -> int:
    config_error = _validate_config()
    if config_error is not None:
        print(f"error: {config_error}", file=sys.stderr)
        return 1

    period_start, period_end = current_month_period()
    try:
        await db_manager.initialize()
        async with get_metadata_session_maker()() as session:
            result = await charge_monthly_usage_for_all_tenants(
                session=session,
                period_start=period_start,
                period_end=period_end,
            )
    except (ValueError, SQLAlchemyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        if db_manager.engine is not None:
            await db_manager.close()

    print(
        json.dumps(
            {
                "tenants_charged": result.tenants_charged,
                "tenants_skipped": result.tenants_skipped,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "details": result.details,
            },
        ),
    )
    logger.info(
        "monthly_usage_billing_complete",
        tenants_charged=result.tenants_charged,
        tenants_skipped=result.tenants_skipped,
    )
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
