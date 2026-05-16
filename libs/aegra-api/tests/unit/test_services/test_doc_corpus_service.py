"""Unit tests for documentation corpus helpers."""

import math

import pytest

from aegra_api.services.doc_corpus_service import (
    cosine_distance_row,
    parse_firecrawl_scrape_payload,
    split_text_into_chunks,
)


def test_parse_firecrawl_scrape_payload_success() -> None:
    markdown, meta = parse_firecrawl_scrape_payload(
        {"success": True, "data": {"markdown": "# Hello", "metadata": {"title": "Hi"}}}
    )
    assert markdown == "# Hello"
    assert meta["title"] == "Hi"


def test_parse_firecrawl_scrape_payload_failure() -> None:
    with pytest.raises(ValueError, match="oops"):
        parse_firecrawl_scrape_payload({"success": False, "error": "oops"})


def test_split_text_into_chunks_returns_empty_for_blank() -> None:
    assert split_text_into_chunks("", max_chars=100, overlap_chars=10) == []
    assert split_text_into_chunks("   \n", max_chars=100, overlap_chars=10) == []


def test_split_text_into_chunks_splits_with_overlap() -> None:
    text = "abcdefgh" * 50
    chunks = split_text_into_chunks(text, max_chars=40, overlap_chars=8)
    assert len(chunks) >= 2
    assert all(len(c) <= 40 for c in chunks)
    # Overlapping windows duplicate boundary text; ensure every chunk is a substring of the source.
    for chunk in chunks:
        assert chunk in text


def test_split_text_into_chunks_clamps_overlap_when_invalid() -> None:
    text = "word " * 30
    chunks = split_text_into_chunks(text, max_chars=20, overlap_chars=50)
    assert chunks
    assert all(len(c) <= 20 for c in chunks)


def test_cosine_distance_row_identical_vectors_is_zero() -> None:
    v = [1.0, 0.0, 0.0]
    assert cosine_distance_row(v, v) == pytest.approx(0.0)


def test_cosine_distance_row_orthogonal_vectors_is_one() -> None:
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert cosine_distance_row(a, b) == pytest.approx(1.0)


def test_cosine_distance_row_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="dimension mismatch"):
        cosine_distance_row([1.0], [1.0, 0.0])


def test_cosine_distance_row_zero_vector_handled() -> None:
    assert cosine_distance_row([0.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert math.isfinite(cosine_distance_row([0.0, 0.0], [0.0, 0.0]))
