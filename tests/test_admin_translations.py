"""Tests for admin access and the translations management page."""

import pytest
from litestar.testing import AsyncTestClient

from src.auth import DEFAULT_ADMIN_USERNAME, ensure_default_admin
from src.i18n.service import clear_translation_cache, load_catalog
from src.models import UIText, User


async def _make_admin_client(client: AsyncTestClient) -> User:
    """Promote the logged-in default user to admin."""
    user = await User.get(username="testuser")
    await User.filter(id=user.id).update(is_admin=True)
    return await User.get(id=user.id)


@pytest.mark.asyncio
async def test_ensure_default_admin_marks_erick(
    anon_client: AsyncTestClient,
) -> None:
    """The configured Erick username should receive admin access."""
    erick = await User.create(username=DEFAULT_ADMIN_USERNAME, email="")
    other = await User.create(username="other", email="")

    await ensure_default_admin()
    await erick.refresh_from_db()
    await other.refresh_from_db()

    assert erick.is_admin is True
    assert other.is_admin is False


@pytest.mark.asyncio
async def test_non_admin_does_not_see_admin_nav(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Admin section links should be hidden for regular users."""
    response = await test_client.get("/")

    assert response.status_code == 200
    assert "/admin/users" not in response.text
    assert "/admin/translations" not in response.text
    assert default_user.is_admin is False


@pytest.mark.asyncio
async def test_admin_sees_admin_nav(test_client: AsyncTestClient) -> None:
    """Admin users should see Admin section links on the home page."""
    await _make_admin_client(test_client)

    response = await test_client.get("/")

    assert response.status_code == 200
    assert "/admin/users" in response.text
    assert "/admin/translations" in response.text


@pytest.mark.asyncio
async def test_non_admin_admin_routes_return_403(
    test_client: AsyncTestClient,
) -> None:
    """Admin routes should forbid non-admin users."""
    users = await test_client.get("/admin/users")
    translations = await test_client.get("/admin/translations")
    save = await test_client.post(
        "/admin/translations/save",
        data={
            "key": "nav.admin",
            "language": "nl",
            "english_text": "Admin",
            "selected_text": "Beheer",
        },
    )

    assert users.status_code == 403
    assert translations.status_code == 403
    assert save.status_code == 403


@pytest.mark.asyncio
async def test_admin_users_placeholder_ok(test_client: AsyncTestClient) -> None:
    """Admins can open the users placeholder page."""
    await _make_admin_client(test_client)

    response = await test_client.get("/admin/users")

    assert response.status_code == 200
    assert "Users" in response.text or "Gebruikers" in response.text


@pytest.mark.asyncio
async def test_admin_translations_page_and_filters(
    test_client: AsyncTestClient,
) -> None:
    """Admins can open translations and filter the list by group and search."""
    await _make_admin_client(test_client)

    page = await test_client.get("/admin/translations")
    assert page.status_code == 200
    assert "translations-filters" in page.text
    assert 'name="group"' in page.text

    filtered = await test_client.get(
        "/admin/translations/list",
        params={"language": "nl", "group": "nav", "search": "admin"},
    )
    assert filtered.status_code == 200
    assert "nav.admin" in filtered.text
    assert "home.lead" not in filtered.text

    incomplete = await test_client.get(
        "/admin/translations/list",
        params={"language": "fr", "incomplete_only": "on", "search": "nav.admin"},
    )
    assert incomplete.status_code == 200
    assert "nav.admin" in incomplete.text
    assert "translations-row--incomplete" in incomplete.text


@pytest.mark.asyncio
async def test_admin_translations_save_updates_texts(
    test_client: AsyncTestClient,
) -> None:
    """Saving a row should upsert English and selected-language UIText values."""
    await _make_admin_client(test_client)
    key = "nav.translations"

    response = await test_client.post(
        "/admin/translations/save",
        data={
            "key": key,
            "language": "nl",
            "english_text": "Translations EN",
            "selected_text": "Vertalingen NL",
        },
    )

    assert response.status_code == 200
    assert "Saved" in response.text or "Opgeslagen" in response.text

    english = await UIText.get(language_code="en", key=key)
    dutch = await UIText.get(language_code="nl", key=key)
    assert english.text == "Translations EN"
    assert dutch.text == "Vertalingen NL"

    clear_translation_cache()
    catalog_nl = await load_catalog("nl")
    assert catalog_nl[key] == "Vertalingen NL"


@pytest.mark.asyncio
async def test_anon_admin_route_redirects_to_login(
    anon_client: AsyncTestClient,
) -> None:
    """Unauthenticated visitors should be redirected before the admin check."""
    response = await anon_client.get("/admin/translations", follow_redirects=False)
    assert response.status_code in {302, 303}
    assert "/login" in response.headers.get("location", "")
