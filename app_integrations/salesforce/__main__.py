"""Extract text from a Salesforce docs PDF: ``python -m app_integrations.salesforce``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf

from app_integrations.salesforce.doc_generation.pdf_embedder import (
    extract_pdf_pages,
    split_salesforce_pdf_into_chunks,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract text from a Salesforce documentation PDF.")
    parser.add_argument(
        "pdf_path",
        nargs="?",
        default=None,
        help="Path to the PDF (defaults to ~/Downloads/sf_docs_pdf.pdf if present)",
    )
    parser.add_argument(
        "--page",
        type=int,
        action="append",
        dest="pages",
        help="Print full text for specific page number(s); repeat flag for multiple pages",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Print full text for every page",
    )
    parser.add_argument(
        "--chunks",
        action="store_true",
        help="Print section-based embedding chunks instead of raw pages",
    )
    return parser


def _resolve_pdf_path(raw: str | None) -> Path:
    if raw is not None:
        return Path(raw).expanduser().resolve()

    downloads_candidate = Path.home() / "Downloads" / "sf_docs_pdf.pdf"
    if downloads_candidate.is_file():
        return downloads_candidate

    msg = "provide a PDF path or place sf_docs_pdf.pdf in Downloads"
    raise ValueError(msg)


def _print_page_text(*, page_number: int, heading: str | None, text: str) -> None:
    title = heading or "(no heading)"
    print(f"=== Page {page_number}: {title} ===")
    print(text)
    print()


def _chunk_matches_pages(chunk_pages: tuple[int, int], wanted_pages: set[int]) -> bool:
    start_page, end_page = chunk_pages
    return any(start_page <= page <= end_page for page in wanted_pages)


def _print_chunk(*, index: int, chunk_title: str, content: str, metadata: dict[str, object]) -> None:
    start_page = metadata.get("start_page")
    end_page = metadata.get("end_page")
    print(f"=== Chunk {index}: {chunk_title} (pages {start_page}-{end_page}) ===")
    print(content)
    print()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        pdf_path = _resolve_pdf_path(args.pdf_path)
    except (ValueError, OSError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    with pymupdf.open(pdf_path) as document:
        doc_title = document.metadata.get("title") or pdf_path.name
        page_count = document.page_count

    if args.chunks:
        try:
            chunks = split_salesforce_pdf_into_chunks(pdf_path, document_title=doc_title)
        except (ValueError, OSError) as err:
            print(f"error: {err}", file=sys.stderr)
            return 1

        print(f"file: {pdf_path}")
        print(f"title: {doc_title}")
        print(f"pages: {page_count}")
        print(f"chunks: {len(chunks)}")
        print()

        if args.pages:
            wanted = set(args.pages)
            selected = [
                chunk
                for chunk in chunks
                if _chunk_matches_pages(
                    (
                        int(chunk.metadata["start_page"]),
                        int(chunk.metadata["end_page"]),
                    ),
                    wanted,
                )
            ]
        elif args.all:
            selected = chunks
        else:
            selected = chunks[:5]
            print("first chunks (use --all or --page N with --chunks for more):")
            print()

        for index, chunk in enumerate(selected, start=1):
            _print_chunk(
                index=index,
                chunk_title=chunk.chunk_title,
                content=chunk.content,
                metadata=chunk.metadata,
            )
        return 0

    try:
        pages = extract_pdf_pages(pdf_path)
    except (ValueError, OSError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    total_chars = sum(page.char_count for page in pages)
    print(f"file: {pdf_path}")
    print(f"title: {doc_title}")
    print(f"pages: {len(pages)}")
    print(f"chars: {total_chars}")
    print()

    if args.all:
        selected = pages
    elif args.pages:
        wanted = set(args.pages)
        selected = [page for page in pages if page.page_number in wanted]
        missing = sorted(wanted - {page.page_number for page in selected})
        for page_number in missing:
            print(f"warning: page {page_number} not found", file=sys.stderr)
    else:
        default_pages = [1, 11, 51]
        page_by_number = {page.page_number: page for page in pages}
        selected = [page_by_number[n] for n in default_pages if n in page_by_number]
        print("sample pages (use --page N or --all for more):")
        print()

    for page in selected:
        _print_page_text(page_number=page.page_number, heading=page.heading, text=page.text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
