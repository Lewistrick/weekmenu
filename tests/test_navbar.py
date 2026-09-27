"""Tests for the navbar dropdown menus."""

import re
from pathlib import Path

import pytest
from litestar.testing import AsyncTestClient


@pytest.mark.asyncio
async def test_nav_menus_are_mutually_exclusive(test_client: AsyncTestClient) -> None:
    """All navbar dropdowns share a details name, so opening one closes the rest."""
    page = await test_client.get("/")

    groups = re.findall(r'<details class="nav-group[^"]*"([^>]*)>', page.text)
    assert len(groups) >= 2
    assert all('name="nav-menu"' in attrs for attrs in groups)


def test_nav_menus_are_full_width_on_mobile() -> None:
    """On narrow screens dropdowns span the links row instead of their button.

    The selector must outrank `.nav-group--right .nav-group-menu` (which pins
    Settings to its button's right edge), whatever the source order.
    """
    css = Path("src/static/css/layout.css").read_text(encoding="utf-8")
    mobile = css.split("@media (max-width: 768px)", 1)[1]

    assert ".navbar-links .nav-group {\n        position: static;" in mobile
    rule = mobile.split(".navbar-links .nav-group .nav-group-menu {", 1)[1]
    rule = rule.split("}", 1)[0]
    assert "left: 0;" in rule
    assert "right: 0;" in rule
