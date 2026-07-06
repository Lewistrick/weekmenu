"""Tests for application-level routes."""

import pytest
from litestar.testing import AsyncTestClient

from src.app import app


@pytest.fixture
async def test_client() -> AsyncTestClient:
    """Provide a test client without initializing the database."""
    async with AsyncTestClient(app=app) as client:
        yield client


@pytest.mark.asyncio
async def test_favicon_is_available(test_client: AsyncTestClient) -> None:
    """Browsers request /favicon.ico automatically; it should not return 404."""
    response = await test_client.get("/favicon.ico")

    assert response.status_code == 200
    assert "image/svg+xml" in response.headers.get("content-type", "")
    assert b"<svg" in response.content
