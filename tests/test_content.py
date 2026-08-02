"""Tests for content-generation helpers (pure functions)."""

from __future__ import annotations

from content import format_and_limit_tags, limit_title


def test_limit_title_short() -> None:
    """Short titles are returned unchanged."""
    assert limit_title("Hello World") == "Hello World"


def test_limit_title_long() -> None:
    """Long titles are trimmed to 100 characters."""
    long_title = "x" * 200
    result = limit_title(long_title)
    assert len(result) <= 100


def test_limit_title_strips_newlines() -> None:
    """Newlines are replaced with spaces."""
    assert limit_title("Line1\nLine2") == "Line1 Line2"


def test_format_and_limit_tags_commas() -> None:
    """Comma-separated tags are normalized and always-first tags prepended."""
    result = format_and_limit_tags("python, ai, github")
    assert result.startswith("foryou, github")
    assert "python" in result
    assert "ai" in result


def test_format_and_limit_tags_removes_hashes() -> None:
    """Hash symbols are stripped from tags."""
    result = format_and_limit_tags("#python, #ai")
    assert "#" not in result


def test_format_and_limit_tags_length() -> None:
    """The result never exceeds the maximum length."""
    result = format_and_limit_tags("tag1, tag2, tag3, tag4, tag5")
    assert len(result) <= 450


def test_format_and_limit_tags_adds_generic() -> None:
    """Generic tags are appended when missing."""
    result = format_and_limit_tags("python")
    assert "open source" in result
