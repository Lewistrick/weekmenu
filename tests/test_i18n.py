"""Tests for UI translation seeding, lookup, and page rendering."""

import pytest
from litestar.testing import AsyncTestClient

from src.i18n.service import (
    DEFAULT_LANGUAGE_CODE,
    DUTCH_LANGUAGE_CODE,
    clear_translation_cache,
    load_catalog,
    seed_dutch_texts,
    seed_english_texts,
    t,
)
from src.models import UIText


@pytest.mark.asyncio
async def test_seed_english_texts_populates_database(
    test_client: AsyncTestClient,
) -> None:
    """Seeding should upsert English strings into the uitext table."""
    clear_translation_cache()
    await seed_english_texts()

    count = await UIText.filter(language_code=DEFAULT_LANGUAGE_CODE).count()
    assert count > 0

    row = await UIText.get(language_code=DEFAULT_LANGUAGE_CODE, key="app.name")
    assert row.text == "Weekmenu"


@pytest.mark.asyncio
async def test_seed_dutch_texts_populates_database(
    test_client: AsyncTestClient,
) -> None:
    """Seeding should upsert Dutch strings into the uitext table."""
    clear_translation_cache()
    await seed_dutch_texts()

    count = await UIText.filter(language_code=DUTCH_LANGUAGE_CODE).count()
    assert count > 0

    row = await UIText.get(language_code=DUTCH_LANGUAGE_CODE, key="home.lead")
    assert "Welkom" in row.text


@pytest.mark.asyncio
async def test_database_texts_exclude_icons(test_client: AsyncTestClient) -> None:
    """Seeded database rows should store text without hardcoded icons."""
    clear_translation_cache()
    await seed_english_texts()

    row = await UIText.get(language_code=DEFAULT_LANGUAGE_CODE, key="nav.week_menu")
    assert row.text == "Week menu"

    mark_all = await UIText.get(
        language_code=DEFAULT_LANGUAGE_CODE, key="grocery.action.mark_all"
    )
    assert mark_all.text == "Check all"


@pytest.mark.asyncio
async def test_t_applies_icons_for_configured_keys(
    test_client: AsyncTestClient,
) -> None:
    """t() should add language-independent icons at render time."""
    clear_translation_cache()
    await seed_english_texts()
    catalog = await load_catalog(DEFAULT_LANGUAGE_CODE)

    from src.i18n import service as i18n_service

    i18n_service._current_catalog.set(catalog)
    i18n_service._fallback_catalog.set(catalog)

    assert t("nav.week_menu").startswith("🗓")
    assert "Week menu" in t("nav.week_menu")
    assert t("grocery.action.mark_all") == "Check all"
    assert t("grocery.action.mark_all.confirm") == "Check all?"


@pytest.mark.asyncio
async def test_t_uses_dutch_catalog_when_loaded(test_client: AsyncTestClient) -> None:
    """t() should return Dutch strings when the Dutch catalog is active."""
    clear_translation_cache()
    await seed_english_texts()
    await seed_dutch_texts()

    dutch = await load_catalog(DUTCH_LANGUAGE_CODE)
    english = await load_catalog(DEFAULT_LANGUAGE_CODE)

    from src.i18n import service as i18n_service

    i18n_service._current_catalog.set(dutch)
    i18n_service._fallback_catalog.set(english)

    assert t("home.lead").startswith("Welkom")
    assert t("auth.login.subtitle") == "Log in om je week te plannen."


@pytest.mark.asyncio
async def test_t_falls_back_to_english_catalog(test_client: AsyncTestClient) -> None:
    """Unknown keys in a sparse catalog should fall back to English."""
    clear_translation_cache()
    await seed_english_texts()

    sparse: dict[str, str] = {"home.lead": "Alleen deze regel"}
    english = await load_catalog(DEFAULT_LANGUAGE_CODE)

    from src.i18n import service as i18n_service

    i18n_service._current_catalog.set(sparse)
    i18n_service._fallback_catalog.set(english)

    assert t("home.lead") == "Alleen deze regel"
    assert t("app.name") == "Weekmenu"


@pytest.mark.asyncio
async def test_t_interpolates_placeholders(test_client: AsyncTestClient) -> None:
    """t() should format placeholders from kwargs."""
    clear_translation_cache()
    await seed_english_texts()
    catalog = await load_catalog(DEFAULT_LANGUAGE_CODE)

    from src.i18n import service as i18n_service

    i18n_service._current_catalog.set(catalog)
    i18n_service._fallback_catalog.set(catalog)

    result = t("message.recipe.deleted", name="Pasta")
    assert result == "Recipe deleted: Pasta"


@pytest.mark.asyncio
async def test_home_page_renders_translated_title(test_client: AsyncTestClient) -> None:
    """The home page should render seeded English UI strings."""
    response = await test_client.get("/")

    assert response.status_code == 200
    assert "Weekmenu" in response.text
    assert "Plan dinners for the week with random picks and pins." in response.text


@pytest.mark.asyncio
async def test_login_page_renders_translated_strings(
    anon_client: AsyncTestClient,
) -> None:
    """The login page should use translated strings without authentication."""
    response = await anon_client.get("/login")

    assert response.status_code == 200
    assert "Log in to plan your week." in response.text
    assert "Create one" in response.text
