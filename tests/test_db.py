"""Tests for the SQLite persistence layer."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import db


@pytest.fixture()
def temp_db(tmp_path: Path) -> None:
    """Point the DB at a temporary file for each test."""
    db.DB_PATH = tmp_path / "test.db"
    db.init_db()


def test_add_and_get_job(temp_db: None) -> None:
    """A job can be added and retrieved by id."""
    job_id = db.add_job("https://github.com/a/b", "/tmp/v.mp4", "/tmp/d.json")
    job = db.get_job_by_id(job_id)
    assert job is not None
    assert job["source_link"] == "https://github.com/a/b"
    assert job["status"] == "pending"


def test_get_next_job_claims_pending(temp_db: None) -> None:
    """get_next_job returns the oldest pending job and marks it processing."""
    db.add_job("https://github.com/a/b", "/tmp/v.mp4", "/tmp/d.json")
    job = db.get_next_job()
    assert job is not None
    assert job["status"] == "processing"
    # Second call returns None (no more pending jobs).
    assert db.get_next_job() is None


def test_get_next_job_empty(temp_db: None) -> None:
    """get_next_job returns None when the queue is empty."""
    assert db.get_next_job() is None


def test_update_job_status(temp_db: None) -> None:
    """Job status can be updated."""
    job_id = db.add_job("https://github.com/a/b", "/tmp/v.mp4", "/tmp/d.json")
    db.update_job_status(job_id, "completed")
    assert db.get_job_by_id(job_id)["status"] == "completed"


def test_update_job_status_invalid(temp_db: None) -> None:
    """Updating with an invalid status raises ValueError."""
    job_id = db.add_job("https://github.com/a/b", "/tmp/v.mp4", "/tmp/d.json")
    with pytest.raises(ValueError):
        db.update_job_status(job_id, "bogus")


def test_get_job_by_id_missing(temp_db: None) -> None:
    """get_job_by_id returns None for a missing job."""
    assert db.get_job_by_id(999) is None
