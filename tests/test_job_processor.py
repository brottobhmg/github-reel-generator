"""Tests for the job processor client using a mocked HTTP layer."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from job_processor import JobProcessor


class FakeTransport(httpx.MockTransport):
    """A mock transport that serves the polling API contract."""

    def __init__(self) -> None:
        super().__init__(self._handler)
        self.completed: list[int] = []
        self.failed: list[int] = []

    def _handler(self, request: httpx.Request) -> httpx.Response:
        url = request.url.path
        if url == "/api/download/1/video":
            return httpx.Response(200, content=b"fake-video-bytes")
        if url == "/api/download/1/json":
            return httpx.Response(
                200,
                json={
                    "descrizione_post": "A description",
                    "tag": "tech, python",
                    "titolo": "A title",
                },
            )
        if url == "/api/job-completed/1":
            self.completed.append(1)
            return httpx.Response(200, json={"status": "success"})
        if url == "/api/job-failed/1":
            self.failed.append(1)
            return httpx.Response(200, json={"status": "success"})
        return httpx.Response(404)


@pytest.fixture()
def processor() -> tuple[JobProcessor, FakeTransport]:
    """Build a JobProcessor backed by a fake transport."""
    transport = FakeTransport()
    client = httpx.Client(transport=transport)
    proc = JobProcessor(base_url="http://testserver", client=client)
    return proc, transport


def test_download_video(processor: tuple[JobProcessor, FakeTransport], tmp_path: Path) -> None:
    """download_video writes the video bytes to disk."""
    proc, _ = processor
    dest = proc.download_video(1, tmp_path)
    assert dest.exists()
    assert dest.read_bytes() == b"fake-video-bytes"


def test_download_json(processor: tuple[JobProcessor, FakeTransport]) -> None:
    """download_json returns the parsed metadata."""
    proc, _ = processor
    data = proc.download_json(1)
    assert data["titolo"] == "A title"
    assert data["tag"] == "tech, python"


def test_notify_completed(processor: tuple[JobProcessor, FakeTransport]) -> None:
    """notify_completed calls the completion endpoint."""
    proc, transport = processor
    proc.notify_completed(1)
    assert transport.completed == [1]


def test_notify_failed(processor: tuple[JobProcessor, FakeTransport]) -> None:
    """notify_failed calls the failure endpoint."""
    proc, transport = processor
    proc.notify_failed(1)
    assert transport.failed == [1]
