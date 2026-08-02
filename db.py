"""SQLite persistence layer for media jobs.

Provides a small, dependency-free data-access layer used by both the FastAPI
server and the Telegram bot.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
from pathlib import Path

from logging_config import get_logger

logger = get_logger(__name__)

DB_PATH = Path(__file__).resolve().parent / "database.db"

#: Allowed job statuses.
VALID_STATUSES = ("pending", "processing", "completed", "failed")


def _connect() -> sqlite3.Connection:
    """Open a connection to the SQLite database."""
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """Create the ``media_jobs`` table if it does not exist."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS media_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_link TEXT NOT NULL,
                mp4_path TEXT NOT NULL,
                json_path TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def add_job(source_link: str, mp4_path: str, json_path: str) -> int:
    """Insert a new pending job.

    Args:
        source_link: The source repository URL.
        mp4_path: Absolute path to the video file.
        json_path: Absolute path to the JSON metadata file.

    Returns:
        The new job id.
    """
    conn = _connect()
    try:
        cursor = conn.cursor()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor.execute(
            "INSERT INTO media_jobs (source_link, mp4_path, json_path, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (source_link, mp4_path, json_path, "pending", now, now),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def get_next_job() -> dict | None:
    """Atomically claim the next pending job.

    Returns:
        The claimed job as a dict, or ``None`` if the queue is empty.
    """
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            "SELECT * FROM media_jobs WHERE status = 'pending' ORDER BY id ASC LIMIT 1"
        )
        row = cursor.fetchone()
        if row:
            job_id = row["id"]
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cursor.execute(
                "UPDATE media_jobs SET status = 'processing', updated_at = ? WHERE id = ?",
                (now, job_id),
            )
            conn.commit()
            job = dict(row)
            job["status"] = "processing"
            return job
        conn.commit()
        return None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_job_status(job_id: int, status: str) -> None:
    """Update the status of a job.

    Args:
        job_id: The job identifier.
        status: One of :data:`VALID_STATUSES`.
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    conn = _connect()
    try:
        cursor = conn.cursor()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor.execute(
            "UPDATE media_jobs SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_job_by_id(job_id: int) -> dict | None:
    """Fetch a job by id.

    Args:
        job_id: The job identifier.

    Returns:
        The job as a dict, or ``None`` if not found.
    """
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM media_jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
