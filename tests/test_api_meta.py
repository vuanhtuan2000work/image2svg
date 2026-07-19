"""FastAPI smoke tests for public meta/index endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from image2svg.web.app import app

client = TestClient(app)


def test_meta_endpoint_shape() -> None:
    res = client.get("/api/meta")
    assert res.status_code == 200
    payload = res.json()
    assert "parts" in payload
    assert "eye" in payload["parts"]
    assert "smoothingLevels" in payload
    assert "outputTypes" in payload
    assert "svg" in payload["outputTypes"]


def test_index_and_analyze_pages() -> None:
    index = client.get("/")
    assert index.status_code == 200
    assert "text/html" in index.headers.get("content-type", "")

    analyze = client.get("/analyze")
    assert analyze.status_code == 200
    assert "text/html" in analyze.headers.get("content-type", "")
