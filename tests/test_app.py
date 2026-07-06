"""Tests for application startup and configuration."""
from pathlib import Path

from litestar.contrib.jinja import JinjaTemplateEngine

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
