"""Ingest GitHub Docs into the documentation corpus: ``python -m app_integrations.github``."""

from __future__ import annotations

import asyncio
import sys

from openai import OpenAIError
from sqlalchemy.exc import SQLAlchemyError

from aegra_api.core.database import db_manager
from aegra_api.core.orm import get_metadata_session_maker
from app_integrations.github.doc_generation import ingest_github_documentation_from_zip


async def _async_main() -> int:
    try:
        await db_manager.initialize()
        async with get_metadata_session_maker()() as session:
            _urls, _chunks, row_titles = await ingest_github_documentation_from_zip(session)
    except (ValueError, RuntimeError, SQLAlchemyError, OpenAIError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    finally:
        if db_manager.engine is not None:
            await db_manager.close()

    for title in row_titles:
        print(title)
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
