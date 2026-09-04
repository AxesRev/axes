"""Ingest Salesforce docs: ``python -m aegra_api.doc_ingest.salesforce <pdf>``."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from openai import OpenAIError
from sqlalchemy.exc import SQLAlchemyError

from aegra_api.core.database import db_manager
from aegra_api.core.orm import get_metadata_session_maker
from aegra_api.doc_ingest.salesforce_pdf import ingest_salesforce_documentation_from_pdf


async def _async_main(pdf_path: Path) -> int:
    try:
        await db_manager.initialize()
        async with get_metadata_session_maker()() as session:
            _pdfs, _chunks, row_titles = await ingest_salesforce_documentation_from_pdf(session, pdf_path)
    except (ValueError, RuntimeError, SQLAlchemyError, OpenAIError, FileNotFoundError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    finally:
        if db_manager.engine is not None:
            await db_manager.close()

    unique_titles = sorted(set(row_titles))
    print(f"ingested pdfs={_pdfs} chunks={_chunks} unique_titles={len(unique_titles)}")
    for title in unique_titles[:20]:
        print(title)
    if len(unique_titles) > 20:
        print(f"... {len(unique_titles) - 20} more titles")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: python -m aegra_api.doc_ingest.salesforce <pdf-path>", file=sys.stderr)
        return 1

    return asyncio.run(_async_main(Path(args[0])))


if __name__ == "__main__":
    raise SystemExit(main())
