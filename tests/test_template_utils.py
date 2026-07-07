"""Tests for Jinja template helpers."""

from src.template_utils import render_markdown


def test_render_markdown_numbered_list() -> None:
    """Numbered steps should render as an ordered list."""
    text = "1. Kook de rijst.\n2. Snijd de groenten."
    html = render_markdown(text)

    assert "<ol>" in html
    assert "<li>Kook de rijst.</li>" in html
    assert "<li>Snijd de groenten.</li>" in html


def test_render_markdown_empty() -> None:
    """Empty descriptions should render as an empty string."""
    assert render_markdown("") == ""
    assert render_markdown(None) == ""


def test_render_markdown_links() -> None:
    """Markdown links should render as anchor tags."""
    html = render_markdown("See [the docs](https://example.com/recipe).")

    assert '<a href="https://example.com/recipe">the docs</a>' in html
