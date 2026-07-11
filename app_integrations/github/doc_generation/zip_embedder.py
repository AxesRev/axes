"""GitHub documentation zip parsing, chunking, and embedding ingestion."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import frontmatter
import structlog
import yaml
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from tqdm import tqdm

from aegra_api.core.orm import DocEmbeddingChunk
from aegra_api.services.doc_corpus_service import embed_texts_openai, split_text_into_chunks
from aegra_api.settings import settings

logger = structlog.get_logger(__name__)

_DOC_INGEST_APPLICATION = "github"
_DOC_INGEST_COLLECTION_KEY = "default"


@dataclass(frozen=True, slots=True)
class _PendingGithubDocChunk:
    """One chunk row waiting for batched embedding and DB insert."""

    content: str
    chunk_display_title: str
    zip_meta: dict[str, Any]


# GitHub Docs zip: hierarchical chunk thresholds (characters, post-frontmatter body).
_GITHUB_DOCS_SMALL_FILE_MAX_CHARS = 2048
_GITHUB_DOCS_HEADER_STRATEGY_UPPER_MAX_CHARS = 98304  # 96 KiB
_GITHUB_DOCS_H2_BLOCK_SUBDIVIDE_CHARS = 4096


def _safe_zip_inner_path(name: str) -> str | None:
    """Reject zip members with absolute paths or ``..`` segments."""
    path = Path(name)
    if path.is_absolute():
        return None
    if ".." in path.parts:
        return None
    return path.as_posix()


def _github_docs_frontmatter_post(markdown: str, *, member: str) -> frontmatter.Post:
    """Parse optional YAML frontmatter and markdown body using ``python-frontmatter``."""
    text = markdown.lstrip("\ufeff")
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        found_close = False
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                found_close = True
                break
        if not found_close:
            raise ValueError(f"github docs markdown has unclosed YAML frontmatter: {member!r}")
    try:
        return frontmatter.loads(text)
    except yaml.YAMLError as exc:
        logger.warning("github_docs_frontmatter_yaml_invalid", member=member, error=str(exc))
        return frontmatter.Post(content=text)


def _strip_markdown_inline_html_comment_suffix(fragment: str) -> str:
    """Remove a trailing ``<!-- ... -->`` suffix from a heading fragment."""
    if "<!--" not in fragment:
        return fragment.strip()
    return fragment.split("<!--", maxsplit=1)[0].strip()


def _first_h1_heading_line_text(markdown: str) -> str | None:
    """Return text of the first ATX ``#`` heading line (not ``##`` / ``###``)."""
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line.startswith("#") or line.startswith("##"):
            continue
        matched = re.match(r"^#\s+(.+)$", line)
        if not matched:
            continue
        title = _strip_markdown_inline_html_comment_suffix(matched.group(1))
        if title:
            return title
    return None


def _metadata_title_string(metadata: dict[str, Any]) -> str | None:
    raw_title = metadata.get("title")
    if isinstance(raw_title, str):
        val = raw_title.strip()
        if val:
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                return val[1:-1]
            return val
    if raw_title is not None and not isinstance(raw_title, (dict, list)):
        val = str(raw_title).strip()
        if val:
            return val
    return None


def _github_docs_document_title_from_post(post: frontmatter.Post, *, member: str) -> str:
    """Corpus document title: YAML ``title:``, else first ``#`` heading in body, else filename stem."""
    yaml_title = _metadata_title_string(post.metadata)
    if yaml_title is not None:
        return yaml_title
    h1 = _first_h1_heading_line_text(post.content)
    if h1 is not None:
        return h1
    return _github_docs_chunk_title_from_member_path(member)


def _github_docs_synthetic_markdown_from_frontmatter(post: frontmatter.Post) -> str | None:
    """Build markdown from YAML when ``post.content`` is empty (GitHub docs index / landing stubs)."""
    meta = post.metadata
    blocks: list[str] = []
    title = _metadata_title_string(meta)
    if title:
        blocks.append(f"# {title}")
    intro = meta.get("intro")
    if isinstance(intro, str) and intro.strip():
        blocks.append(intro.strip())
    children = meta.get("children")
    if isinstance(children, list):
        lines: list[str] = []
        for item in children:
            if isinstance(item, str) and item.strip():
                lines.append(f"- {item.strip()}")
            elif item is not None and not isinstance(item, (dict, list)):
                text_item = str(item).strip()
                if text_item:
                    lines.append(f"- {text_item}")
        if lines:
            blocks.append("\n".join(lines))
    if not blocks:
        return None
    return "\n\n".join(blocks)


def _github_docs_chunking_body_from_post(post: frontmatter.Post, *, document_title: str) -> str:
    """Markdown body used for chunking; synthesize text when the file has YAML only (no body)."""
    body = post.content.strip()
    if body:
        return body
    synthetic = _github_docs_synthetic_markdown_from_frontmatter(post)
    if synthetic is not None:
        return synthetic
    return f"# {document_title}\n"


def _github_docs_zip_document_title(markdown: str, *, member: str) -> str:
    """Same as ``_github_docs_document_title_from_post`` after parsing *markdown*."""
    post = _github_docs_frontmatter_post(markdown, member=member)
    return _github_docs_document_title_from_post(post, member=member)


def _github_docs_chunk_title_from_member_path(zip_member_path: str) -> str:
    """Display title from zip entry path (filename stem without ``.md``)."""
    stem = Path(zip_member_path).stem.strip()
    return stem if stem else zip_member_path


def _section_heading_title_or_file(primary: str, *, file_title: str) -> str:
    candidate = primary.strip()
    return candidate if candidate else file_title


def _first_h2_heading_line_text(body: str) -> str | None:
    """Return the text of the first ``##`` heading line (ignores ``###`` and deeper)."""
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("###"):
            continue
        matched = re.match(r"^##\s+(.+)$", line)
        if matched:
            title = matched.group(1).strip()
            if title:
                return title
    return None


def split_github_docs_zip_markdown_into_chunks(
    body_markdown: str,
    *,
    zip_member_path: str,
    max_chars: int,
    overlap_chars: int,
) -> list[tuple[str, str]]:
    """Split GitHub-docs-style markdown body; returns ``(chunk_text, chunk_title)`` pairs.

    Chunk titles:

    * Whole-file small docs (``len <= 2048``): one chunk; title is the first ``##`` heading if any,
      otherwise the zip entry filename stem.
    * ``##`` sections use that heading line text (without the ``##`` marker).
    * ``###`` subdivisions use ``"{h2} — {h3}"``.
    * Sliding-window splits (oversized sections or huge files) reuse the same section title when
      applicable; otherwise the zip entry filename stem.

    Rules (hardcoded size gates):

    * ``len(body) <= 2048``: one chunk (no split).
    * ``2048 < len(body) <= 98304``: split on top-level ``## `` headings; any ``##`` section longer
      than 4096 chars is subdivided on ``### `` headings.
    * ``len(body) > 98304``: sliding-window chunking over the whole body (same as
      ``split_text_into_chunks``).

    Pieces that remain oversized after ``###`` splits are further split with ``split_text_into_chunks``.
    """
    file_chunk_title = _github_docs_chunk_title_from_member_path(zip_member_path)
    body = body_markdown.strip()
    if not body:
        return []

    n = len(body)
    if n <= _GITHUB_DOCS_SMALL_FILE_MAX_CHARS:
        h2_title = _first_h2_heading_line_text(body)
        chunk_title = (
            _section_heading_title_or_file(h2_title, file_title=file_chunk_title)
            if h2_title is not None
            else file_chunk_title
        )
        return [(body, chunk_title)]

    if n > _GITHUB_DOCS_HEADER_STRATEGY_UPPER_MAX_CHARS:
        return [
            (piece, file_chunk_title)
            for piece in split_text_into_chunks(body, max_chars=max_chars, overlap_chars=overlap_chars)
        ]

    segments = re.split(r"^##\s+", body, flags=re.MULTILINE)
    preamble = segments[0].strip()
    h2_sections: list[tuple[str, str]] = []
    for raw in segments[1:]:
        raw_lines = raw.splitlines()
        h2_title = raw_lines[0].strip() if raw_lines else ""
        section_rest = "\n".join(raw_lines[1:]).strip()
        h2_sections.append((h2_title, section_rest))

    if preamble and h2_sections:
        first_title, first_body = h2_sections[0]
        merged = f"{preamble}\n\n{first_body}".strip() if first_body else preamble
        h2_sections[0] = (first_title, merged)
    elif preamble and not h2_sections:
        merged_body = preamble
        return [
            (piece, file_chunk_title)
            for piece in split_text_into_chunks(merged_body, max_chars=max_chars, overlap_chars=overlap_chars)
        ]

    if not h2_sections:
        return [
            (piece, file_chunk_title)
            for piece in split_text_into_chunks(body, max_chars=max_chars, overlap_chars=overlap_chars)
        ]

    out: list[tuple[str, str]] = []

    def append_or_window(text: str, chunk_title: str) -> None:
        piece = text.strip()
        if not piece:
            return
        resolved_title = _section_heading_title_or_file(chunk_title, file_title=file_chunk_title)
        if len(piece) <= _GITHUB_DOCS_H2_BLOCK_SUBDIVIDE_CHARS:
            out.append((piece, resolved_title))
            return
        for window in split_text_into_chunks(piece, max_chars=max_chars, overlap_chars=overlap_chars):
            out.append((window, resolved_title))

    for h2_title, section_body in h2_sections:
        h2_heading_title = _section_heading_title_or_file(h2_title, file_title=file_chunk_title)
        h2_block = f"## {h2_title}\n\n{section_body}".strip() if section_body else f"## {h2_title}".strip()
        if len(h2_block) <= _GITHUB_DOCS_H2_BLOCK_SUBDIVIDE_CHARS:
            append_or_window(h2_block, h2_heading_title)
            continue

        sub = re.split(r"^###\s+", section_body, flags=re.MULTILINE)
        before_h3 = sub[0].strip()
        head_with_intro = f"## {h2_title}\n\n{before_h3}".strip() if before_h3 else f"## {h2_title}".strip()
        append_or_window(head_with_intro, h2_heading_title)

        for raw_h3 in sub[1:]:
            h3_lines = raw_h3.splitlines()
            h3_title = h3_lines[0].strip() if h3_lines else ""
            h3_rest = "\n".join(h3_lines[1:]).strip()
            h3_block = (
                f"## {h2_title}\n\n### {h3_title}\n\n{h3_rest}".strip()
                if h3_rest
                else (f"## {h2_title}\n\n### {h3_title}".strip())
            )
            h3_heading_title = h3_title.strip()
            if h3_heading_title:
                combined = f"{h2_heading_title} — {h3_heading_title}"
            else:
                combined = h2_heading_title
            append_or_window(h3_block, combined)

    return [(c, t) for c, t in out if c.strip()]


def iter_github_docs_zip_markdown_members(zip_path: Path) -> list[str]:
    """Return sorted safe zip member paths ending in ``.md`` (non-directory).

    Raises:
        ValueError: If the archive contains no ``.md`` files, or any ``.md`` member path is unsafe.
    """
    with zipfile.ZipFile(zip_path, "r") as archive:
        md_members: list[str] = []
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            if not name.lower().endswith(".md"):
                continue
            safe = _safe_zip_inner_path(name)
            if safe is None:
                raise ValueError(f"unsafe zip member path: {name!r}")
            md_members.append(safe)
        md_members.sort()
        if not md_members:
            raise ValueError("zip contains no .md files")
        return md_members


def read_github_docs_zip_markdown(zip_path: Path, inner_path: str) -> str:
    """Read one zip member as strict UTF-8 text."""
    safe = _safe_zip_inner_path(inner_path)
    if safe is None:
        raise ValueError("unsafe zip member path")
    with zipfile.ZipFile(zip_path, "r") as archive, archive.open(safe, "r") as raw:
        data = raw.read()
    return data.decode("utf-8")


async def ingest_github_documentation_from_zip(
    session: AsyncSession,
    *,
    show_progress: bool = True,
) -> tuple[int, int, list[str]]:
    """Ingest markdown files from the zip at ``GITHUB_DOCS_ZIP_PATH``.

    Pipeline: (1) chunk every file into a flat list, (2) one batched embedding pass over all chunk
    texts, (3) insert rows. OpenAI still receives up to 64 strings per HTTP request; batches are
    filled across files.

    Each file should have YAML frontmatter with ``title:`` when possible; otherwise the first ``#``
    heading or the zip entry filename stem is used for ``document_title`` metadata.

    Args:
        show_progress: When ``True``, render tqdm bars for chunking, embedding, and DB writes.

    Returns:
        ``(markdown files ingested, chunk rows inserted, chunk display title per row)``.
    """
    cfg = settings.doc_corpus
    configured = cfg.GITHUB_DOCS_ZIP_PATH
    if configured is None:
        raise ValueError("GITHUB_DOCS_ZIP_PATH is not configured")
    resolved = configured.strip()
    if not resolved:
        raise ValueError("GITHUB_DOCS_ZIP_PATH is empty")
    if not cfg.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured")

    archive_path = Path(resolved)
    if not archive_path.is_file():
        raise ValueError(f"github docs zip not found or not a file: {archive_path}")

    application = _DOC_INGEST_APPLICATION
    collection_key = _DOC_INGEST_COLLECTION_KEY

    await session.execute(
        delete(DocEmbeddingChunk).where(
            DocEmbeddingChunk.application == application,
            DocEmbeddingChunk.collection_key == collection_key,
        )
    )
    await session.commit()

    member_paths = iter_github_docs_zip_markdown_members(archive_path)
    file_total = len(member_paths)
    tqdm_disable = not show_progress
    tqdm_kw: dict[str, Any] = {
        "disable": tqdm_disable,
        "dynamic_ncols": True,
        "leave": True,
    }

    pending: list[_PendingGithubDocChunk] = []

    with tqdm(total=file_total, desc="Chunking", unit="file", position=0, **tqdm_kw) as chunk_bar:
        for inner in member_paths:
            markdown = read_github_docs_zip_markdown(archive_path, inner)
            post = _github_docs_frontmatter_post(markdown, member=inner)
            document_title = _github_docs_document_title_from_post(post, member=inner)
            body = _github_docs_chunking_body_from_post(post, document_title=document_title)

            chunk_pairs = split_github_docs_zip_markdown_into_chunks(
                body,
                zip_member_path=inner,
                max_chars=cfg.DOCS_CHUNK_MAX_CHARS,
                overlap_chars=cfg.DOCS_CHUNK_OVERLAP_CHARS,
            )
            if not chunk_pairs:
                raise ValueError(f"github docs markdown produced no chunks after split: {inner!r}")

            zip_meta: dict[str, Any] = {"zip_member": inner, "document_title": document_title}
            for text_chunk, chunk_title in chunk_pairs:
                pending.append(
                    _PendingGithubDocChunk(
                        content=text_chunk,
                        chunk_display_title=chunk_title,
                        zip_meta=zip_meta,
                    )
                )

            chunk_bar.update(1)

    chunk_total = len(pending)

    with tqdm(total=chunk_total, desc="Embedding", unit="chunk", position=1, **tqdm_kw) as embed_bar:
        embeddings = await embed_texts_openai(
            texts=[row.content for row in pending],
            model=cfg.DOCS_EMBED_MODEL,
            api_key=cfg.OPENAI_API_KEY,
            progress_bar=embed_bar,
        )

    if len(embeddings) != chunk_total:
        raise RuntimeError("embedding count does not match chunk count")

    row_titles: list[str] = []

    with tqdm(total=chunk_total, desc="Storing in DB", unit="chunk", position=2, **tqdm_kw) as store_bar:
        for row, vector in zip(pending, embeddings, strict=True):
            if len(vector) != cfg.DOCS_EMBED_DIMENSIONS:
                raise ValueError("unexpected embedding size from OpenAI")
            session.add(
                DocEmbeddingChunk(
                    application=application,
                    collection_key=collection_key,
                    page_title=row.chunk_display_title,
                    content=row.content,
                    metadata_dict={"github_docs_zip": row.zip_meta},
                    embedding=vector,
                )
            )
            row_titles.append(row.chunk_display_title)
            store_bar.update(1)

    await session.commit()
    files_seen = file_total
    chunks_written = chunk_total
    return files_seen, chunks_written, row_titles
