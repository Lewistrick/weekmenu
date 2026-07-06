"""Jinja template helpers."""

import markdown

_renderer = markdown.Markdown(extensions=["nl2br", "sane_lists"])


def render_markdown(text: str | None) -> str:
    """Render recipe description text as HTML via Markdown.

    Args:
        text: Plain-text or Markdown recipe description.

    Returns:
        HTML string suitable for rendering with the ``safe`` filter.
    """
    if not text:
        return ""
    html = _renderer.convert(text)
    _renderer.reset()
    return html
