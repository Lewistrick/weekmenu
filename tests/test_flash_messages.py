"""Tests for HTMX flash message dismiss behavior."""

import pytest
from litestar.testing import AsyncTestClient

from src.models import Recipe, User


@pytest.mark.asyncio
async def test_flash_messages_include_htmx_dismiss_controls(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Flash messages should auto-dismiss and offer a dismiss button via HTMX."""
    recipe = await Recipe.create(
        name="Flash test",
        description="Test",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
    )

    response = await test_client.post(
        f"/recipes/{recipe.id}/tags",
        data={},
    )

    assert response.status_code == 200
    assert 'hx-trigger="load delay:5s"' in response.text
    assert 'hx-swap="delete"' in response.text
    assert 'aria-label="Dismiss"' in response.text
    assert "Recipe tags updated" in response.text


@pytest.mark.asyncio
async def test_week_menu_warnings_include_htmx_dismiss_controls(
    test_client: AsyncTestClient,
) -> None:
    """Week menu warnings should use the HTMX dismiss partial."""
    for day in [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]:
        await test_client.post(f"/week-menu/{day}/pin")

    response = await test_client.post("/week-menu/randomize")

    assert response.status_code == 200
    assert "week-menu-warning-0" in response.text
    assert 'hx-trigger="load delay:5s"' in response.text
    assert "All days are pinned" in response.text
