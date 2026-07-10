"""Tests for application startup, configuration, and routes."""

from pathlib import Path

import pytest
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.testing import AsyncTestClient

from src.app import app, register_template_filters


def test_app_loads_template_engine() -> None:
    """The Litestar app should initialize its template engine on import."""
    assert app.template_engine is not None


def test_markdown_filter_registered() -> None:
    """The markdown filter should be available on the Jinja environment."""
    assert isinstance(app.template_engine, JinjaTemplateEngine)
    assert "markdown" in app.template_engine.engine.filters


def test_register_template_filters_adds_markdown() -> None:
    """register_template_filters should register the markdown filter."""
    engine = JinjaTemplateEngine(directory=Path("src/templates"))
    register_template_filters(engine)

    assert "markdown" in engine.engine.filters


@pytest.mark.asyncio
async def test_favicon_is_available() -> None:
    """Browsers request /favicon.ico automatically; it should not return 404."""
    async with AsyncTestClient(app=app) as client:
        response = await client.get("/favicon.ico")

    assert response.status_code == 200
    assert "image/svg+xml" in response.headers.get("content-type", "")
    assert b"<svg" in response.content
