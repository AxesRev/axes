"""Salesforce documentation PDF parsing, text extraction, and chunking."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf
import structlog

from aegra_api.services.doc_corpus_service import split_text_into_chunks

logger = structlog.get_logger(__name__)

_TEXT_BLOCK_TYPE = 0
_CHAPTER_HEADING_FONT_SIZE_MIN = 14.0
_SECTION_HEADING_FONT_SIZE_MIN = 10.5
_SECTION_TITLE_MAX_CHARS = 120
_MIN_SECTION_CHARS = 40
_MERGE_SMALL_SECTION_CHARS = 400
_RUNNING_HEADER_MIN_PAGE_FRACTION = 0.08

_PAGE_NUMBER_ONLY_RE = re.compile(r"^\d{1,3}$")
_TOC_DOTTED_LINE_RE = re.compile(r"\.(?:\s*\.\s*){2,}\s*\d+\s*$")

_SKIP_LINE_PREFIXES = (
    "SEE ALSO:",
    "IN THIS SECTION:",
    "Tip:",
    "Note:",
)
_SUBSECTION_LABELS = frozenset({"Examples", "Reference", "Further Information"})


@dataclass(frozen=True, slots=True)
class PdfLine:
    """One text line extracted from a PDF page with layout metadata."""

    page_number: int
    text: str
    font_size: float
    y0: float


@dataclass(frozen=True, slots=True)
class SalesforcePdfPageText:
    """Extracted text for one PDF page."""

    page_number: int
    text: str
    heading: str | None
    char_count: int


@dataclass(slots=True)
class PdfSection:
    """A documentation section spanning one or more pages."""

    title: str
    body: str
    start_page: int
    end_page: int
    lines: list[PdfLine] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SalesforcePdfChunk:
    """One chunk ready for embedding."""

    page_number: int
    content: str
    chunk_title: str
    metadata: dict[str, Any]


def _normalize_line(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _sorted_text_blocks(page: pymupdf.Page) -> list[str]:
    blocks = page.get_text("blocks")
    text_blocks = [block for block in blocks if block[6] == _TEXT_BLOCK_TYPE and block[4].strip()]
    ordered = sorted(text_blocks, key=lambda block: (round(block[1], 1), round(block[0], 1)))
    return [block[4].strip() for block in ordered]


def _detect_page_heading(page: pymupdf.Page) -> str | None:
    page_dict = page.get_text("dict")
    max_size = 0.0
    heading_parts: list[str] = []

    for block in page_dict.get("blocks", []):
        if block.get("type") != _TEXT_BLOCK_TYPE:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            line_text = "".join(str(span.get("text", "")) for span in spans).strip()
            if not line_text:
                continue
            line_size = max(float(span.get("size", 0.0)) for span in spans)
            if line_size > max_size + 0.5:
                max_size = line_size
                heading_parts = [line_text]
            elif line_size >= max_size - 0.5 and max_size >= _CHAPTER_HEADING_FONT_SIZE_MIN:
                heading_parts.append(line_text)

    if max_size < _CHAPTER_HEADING_FONT_SIZE_MIN or not heading_parts:
        return None
    return " ".join(heading_parts)


def extract_page_lines(page: pymupdf.Page, *, page_number: int) -> list[PdfLine]:
    """Extract ordered lines with font sizes from one PDF page."""
    page_dict = page.get_text("dict")
    lines: list[PdfLine] = []

    for block in page_dict.get("blocks", []):
        if block.get("type") != _TEXT_BLOCK_TYPE:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(str(span.get("text", "")) for span in spans).strip()
            if not text:
                continue
            font_size = max(float(span.get("size", 0.0)) for span in spans)
            y0 = float(line["bbox"][1])
            lines.append(
                PdfLine(
                    page_number=page_number,
                    text=text,
                    font_size=font_size,
                    y0=y0,
                )
            )

    lines.sort(key=lambda item: (round(item.y0, 1), item.text))
    return lines


def extract_page_text(page: pymupdf.Page, *, page_number: int) -> SalesforcePdfPageText:
    """Extract reading-order text from a single PDF page."""
    block_texts = _sorted_text_blocks(page)
    body = "\n\n".join(block_texts).strip()
    heading = _detect_page_heading(page)
    return SalesforcePdfPageText(
        page_number=page_number,
        text=body,
        heading=heading,
        char_count=len(body),
    )


def extract_pdf_pages(pdf_path: Path) -> list[SalesforcePdfPageText]:
    """Extract text from every page in a Salesforce docs PDF."""
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Salesforce docs PDF not found: {pdf_path}")

    pages: list[SalesforcePdfPageText] = []
    with pymupdf.open(pdf_path) as document:
        for index in range(document.page_count):
            page = document[index]
            pages.append(extract_page_text(page, page_number=index + 1))

    logger.info(
        "salesforce_pdf_extracted",
        pdf_path=str(pdf_path),
        page_count=len(pages),
        total_chars=sum(page.char_count for page in pages),
    )
    return pages


def _is_code_like_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return (
        stripped.startswith("{")
        or stripped.startswith("}")
        or stripped.startswith('"')
        or stripped.startswith("curl ")
        or stripped.startswith("HTTP/")
        or stripped.endswith("{")
        or stripped.endswith(",")
        or '":' in stripped
        or stripped.startswith("<")
        and stripped.endswith(">")
    )


def _lines_to_body(lines: list[PdfLine]) -> str:
    """Join lines into body text, keeping code blocks as contiguous paragraphs."""
    if not lines:
        return ""

    paragraphs: list[str] = []
    buffer: list[str] = []
    buffer_is_code = False

    for line in lines:
        is_code = _is_code_like_line(line.text)
        if not buffer:
            buffer = [line.text]
            buffer_is_code = is_code
            continue

        if is_code == buffer_is_code:
            buffer.append(line.text)
            continue

        joiner = "\n" if buffer_is_code else "\n"
        paragraphs.append(joiner.join(buffer))
        buffer = [line.text]
        buffer_is_code = is_code

    if buffer:
        joiner = "\n" if buffer_is_code else "\n"
        paragraphs.append(joiner.join(buffer))

    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph.strip())


def detect_running_headers(page_lines: list[list[PdfLine]]) -> set[str]:
    """Find short lines repeated across many pages (headers/footers)."""
    counts: Counter[str] = Counter()
    for lines in page_lines:
        seen_on_page: set[str] = set()
        for line in lines:
            normalized = _normalize_line(line.text)
            if not normalized or len(normalized) >= 80:
                continue
            if normalized in seen_on_page:
                continue
            counts[normalized] += 1
            seen_on_page.add(normalized)

    threshold = max(3, int(len(page_lines) * _RUNNING_HEADER_MIN_PAGE_FRACTION))
    return {text for text, count in counts.items() if count >= threshold}


def _is_toc_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.upper() == "CONTENTS":
        return True
    return bool(_TOC_DOTTED_LINE_RE.search(stripped))


def is_toc_page(lines: list[PdfLine]) -> bool:
    """Detect table-of-contents pages to skip during chunking."""
    if not lines:
        return True

    if lines[0].text.strip().lower() == "contents":
        return True

    toc_lines = sum(1 for line in lines if _is_toc_line(line.text))
    return toc_lines >= max(3, len(lines) // 3)


def is_cover_page(lines: list[PdfLine], *, page_number: int) -> bool:
    """Skip title/copyright pages with little embeddable content."""
    if not lines or page_number > 2:
        return False

    joined = " ".join(line.text for line in lines).lower()
    if "copyright" in joined:
        return True

    return page_number == 1 and "developer guide" in joined and len(joined) < 200


def is_nav_page(lines: list[PdfLine]) -> bool:
    """Detect chapter opener/nav pages that are mostly bullet lists."""
    if not lines:
        return True

    short_lines = sum(1 for line in lines if len(line.text) < 45)
    has_chapter_nav = any("In this chapter" in line.text for line in lines)
    return has_chapter_nav and short_lines / len(lines) > 0.55


def _should_skip_line(text: str, *, running_headers: set[str]) -> bool:
    normalized = _normalize_line(text)
    if not normalized:
        return True
    if normalized in running_headers:
        return True
    if _PAGE_NUMBER_ONLY_RE.match(normalized):
        return True
    return any(normalized.startswith(prefix) for prefix in _SKIP_LINE_PREFIXES)


def _is_section_heading(line: PdfLine, *, running_headers: set[str]) -> bool:
    normalized = _normalize_line(line.text)
    if _should_skip_line(normalized, running_headers=running_headers):
        return False
    if normalized in _SUBSECTION_LABELS:
        return False
    if _is_toc_line(normalized):
        return False
    if len(normalized) > _SECTION_TITLE_MAX_CHARS:
        return False
    return line.font_size >= _SECTION_HEADING_FONT_SIZE_MIN


def build_pdf_sections(
    page_lines: list[list[PdfLine]],
    *,
    running_headers: set[str],
) -> list[PdfSection]:
    """Group cleaned PDF lines into documentation sections."""
    sections: list[PdfSection] = []
    current_title: str | None = None
    current_lines: list[PdfLine] = []
    current_start_page: int | None = None
    previous_line_text: str | None = None

    def flush_section() -> None:
        nonlocal current_title, current_lines, current_start_page
        if current_title is None or not current_lines:
            current_title = None
            current_lines = []
            current_start_page = None
            return

        body = _lines_to_body(current_lines).strip()
        if len(body) < _MIN_SECTION_CHARS:
            current_title = None
            current_lines = []
            current_start_page = None
            return

        sections.append(
            PdfSection(
                title=current_title,
                body=body,
                start_page=current_start_page or current_lines[0].page_number,
                end_page=current_lines[-1].page_number,
                lines=list(current_lines),
            )
        )
        current_title = None
        current_lines = []
        current_start_page = None

    for lines in page_lines:
        if not lines:
            continue
        page_number = lines[0].page_number
        if is_toc_page(lines) or is_nav_page(lines) or is_cover_page(lines, page_number=page_number):
            continue

        for line in lines:
            if _should_skip_line(line.text, running_headers=running_headers):
                previous_line_text = line.text
                continue

            normalized = _normalize_line(line.text)
            if _is_section_heading(line, running_headers=running_headers):
                if current_title == normalized:
                    previous_line_text = line.text
                    continue
                if previous_line_text and _normalize_line(previous_line_text) == normalized:
                    previous_line_text = line.text
                    continue

                flush_section()
                current_title = normalized
                current_lines = []
                current_start_page = line.page_number
                previous_line_text = line.text
                continue

            if current_title is None:
                previous_line_text = line.text
                continue

            current_lines.append(line)
            previous_line_text = line.text

    flush_section()
    return sections


def _merge_small_sections(sections: list[PdfSection]) -> list[PdfSection]:
    if not sections:
        return []

    merged: list[PdfSection] = []
    carry: PdfSection | None = None

    for section in sections:
        if carry is None:
            carry = PdfSection(
                title=section.title,
                body=section.body,
                start_page=section.start_page,
                end_page=section.end_page,
                lines=list(section.lines),
            )
            continue

        if len(carry.body) < _MERGE_SMALL_SECTION_CHARS and section.start_page <= carry.end_page + 1:
            carry = PdfSection(
                title=carry.title,
                body=f"{carry.body}\n\n{section.body}".strip(),
                start_page=carry.start_page,
                end_page=section.end_page,
                lines=[*carry.lines, *section.lines],
            )
            continue

        merged.append(carry)
        carry = PdfSection(
            title=section.title,
            body=section.body,
            start_page=section.start_page,
            end_page=section.end_page,
            lines=list(section.lines),
        )

    if carry is not None:
        merged.append(carry)

    return merged


def _paragraphs_from_body(body: str) -> list[str]:
    if not body.strip():
        return []

    lines = body.splitlines()
    paragraphs: list[str] = []
    buffer: list[str] = []
    buffer_is_code = False

    for line in lines:
        is_code = _is_code_like_line(line)
        if not buffer:
            buffer = [line]
            buffer_is_code = is_code
            continue

        if is_code == buffer_is_code:
            buffer.append(line)
            continue

        paragraphs.append("\n".join(buffer).strip())
        buffer = [line]
        buffer_is_code = is_code

    if buffer:
        paragraphs.append("\n".join(buffer).strip())

    return [paragraph for paragraph in paragraphs if paragraph]


def _pack_paragraphs_into_chunks(
    paragraphs: list[str],
    *,
    max_chars: int,
    overlap_chars: int,
) -> list[str]:
    if not paragraphs:
        return []

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    def flush_current() -> None:
        nonlocal current_parts, current_len
        if not current_parts:
            return
        chunks.append("\n\n".join(current_parts).strip())
        current_parts = []
        current_len = 0

    for paragraph in paragraphs:
        paragraph_len = len(paragraph)
        if paragraph_len > max_chars:
            flush_current()
            chunks.extend(
                split_text_into_chunks(
                    paragraph,
                    max_chars=max_chars,
                    overlap_chars=overlap_chars,
                )
            )
            continue

        extra = paragraph_len if not current_parts else paragraph_len + 2
        if current_len + extra > max_chars:
            flush_current()

        current_parts.append(paragraph)
        current_len += extra

    flush_current()
    return chunks


def _format_chunk_content(*, document_title: str, section_title: str, body: str) -> str:
    return f"# {document_title} > {section_title}\n\n{body.strip()}"


def chunk_pdf_sections(
    sections: list[PdfSection],
    *,
    document_title: str,
    max_chars: int,
    overlap_chars: int,
) -> list[SalesforcePdfChunk]:
    """Turn sections into embedding-sized chunks with breadcrumb prefixes."""
    chunks: list[SalesforcePdfChunk] = []

    for section_index, section in enumerate(sections):
        paragraphs = _paragraphs_from_body(section.body)
        bodies = _pack_paragraphs_into_chunks(
            paragraphs,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
        if not bodies and section.body.strip():
            bodies = [section.body.strip()]

        for body in bodies:
            chunks.append(
                SalesforcePdfChunk(
                    page_number=section.start_page,
                    content=_format_chunk_content(
                        document_title=document_title,
                        section_title=section.title,
                        body=body,
                    ),
                    chunk_title=section.title,
                    metadata={
                        "document_title": document_title,
                        "section_title": section.title,
                        "section_index": section_index,
                        "start_page": section.start_page,
                        "end_page": section.end_page,
                        "source_format": "pdf",
                    },
                )
            )

    return chunks


def split_salesforce_pdf_into_chunks(
    pdf_path: Path,
    *,
    max_chars: int = 2000,
    overlap_chars: int = 200,
    document_title: str | None = None,
) -> list[SalesforcePdfChunk]:
    """Extract a Salesforce docs PDF and chunk it by section for embedding."""
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Salesforce docs PDF not found: {pdf_path}")

    with pymupdf.open(pdf_path) as document:
        resolved_title = document_title or document.metadata.get("title") or pdf_path.stem
        all_page_lines = [
            extract_page_lines(document[index], page_number=index + 1) for index in range(document.page_count)
        ]

    running_headers = detect_running_headers(all_page_lines)
    sections = build_pdf_sections(all_page_lines, running_headers=running_headers)
    sections = _merge_small_sections(sections)
    chunks = chunk_pdf_sections(
        sections,
        document_title=resolved_title,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    )

    logger.info(
        "salesforce_pdf_chunked",
        pdf_path=str(pdf_path),
        section_count=len(sections),
        chunk_count=len(chunks),
    )
    return chunks


def split_salesforce_pdf_pages_into_chunks(
    pages: list[SalesforcePdfPageText],
    *,
    max_chars: int,
    overlap_chars: int,
    document_title: str = "Salesforce Documentation",
) -> list[SalesforcePdfChunk]:
    """Chunk already-extracted page text using one section per page (legacy/test helper)."""
    sections = [
        PdfSection(
            title=page.heading or f"Page {page.page_number}",
            body=page.text.strip(),
            start_page=page.page_number,
            end_page=page.page_number,
        )
        for page in pages
        if page.text.strip()
    ]
    return chunk_pdf_sections(
        sections,
        document_title=document_title,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    )
