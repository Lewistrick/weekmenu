"""Tests for authentication and account management."""

import pytest
from litestar.testing import AsyncTestClient

from src.auth import hash_password, verify_password
from src.invite_users import create_invited_user
from src.models import Recipe, User
from src.url_path import base_path, path_with_base
from src.user_settings import load_user_settings
from tests.conftest import DEFAULT_PASSWORD, DEFAULT_USERNAME, register_user


def test_password_hash_roundtrip() -> None:
    """A hashed password should verify against the original and reject others."""
    hashed = hash_password("hunter2!")
    assert hashed != "hunter2!"
    assert verify_password("hunter2!", hashed) is True
    assert verify_password("wrong", hashed) is False
    assert verify_password("anything", None) is False


def test_base_path_defaults_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without APP_BASE_PATH, helpers should leave paths unchanged."""
    monkeypatch.delenv("APP_BASE_PATH", raising=False)
    assert base_path() == ""
    assert path_with_base("/login") == "/login"


def test_base_path_prefixes_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    """With APP_BASE_PATH set, helpers should prefix absolute app paths."""
    monkeypatch.setenv("APP_BASE_PATH", "/weekmenu")
    assert base_path() == "/weekmenu"
    assert path_with_base("/login") == "/weekmenu/login"
    assert path_with_base("/") == "/weekmenu/"


@pytest.mark.asyncio
async def test_protected_route_redirects_anonymous(
    anon_client: AsyncTestClient,
) -> None:
    """Unauthenticated visitors should be redirected to the login page."""
    response = await anon_client.get("/week-menu", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_login_page_is_public(anon_client: AsyncTestClient) -> None:
    """The login page should be reachable without authentication."""
    response = await anon_client.get("/login")

    assert response.status_code == 200
    assert "Log in" in response.text
    assert "/register" not in response.text


@pytest.mark.asyncio
async def test_register_routes_return_404(anon_client: AsyncTestClient) -> None:
    """Public registration endpoints should be unavailable."""
    get_response = await anon_client.get("/register")
    post_response = await anon_client.post(
        "/register",
        data={
            "username": "alice",
            "password": "wonderland",
            "password_confirm": "wonderland",
            "email": "",
        },
    )

    assert get_response.status_code == 404
    assert post_response.status_code == 404
    assert await User.get_by_username("alice") is None


@pytest.mark.asyncio
async def test_login_creates_authenticated_session(
    anon_client: AsyncTestClient,
) -> None:
    """Logging in should start an authenticated session."""
    await register_user(anon_client, username="alice", password="wonderland")

    protected = await anon_client.get("/week-menu", follow_redirects=False)
    assert protected.status_code == 200


@pytest.mark.asyncio
async def test_login_with_wrong_password_fails(anon_client: AsyncTestClient) -> None:
    """Logging in with an incorrect password should show an error."""
    await register_user(anon_client, username="dave", password="correct-horse")
    await anon_client.post("/logout")

    response = await anon_client.post(
        "/login",
        data={"username": "dave", "password": "wrong"},
    )

    assert response.status_code == 200
    assert "Invalid username or password" in response.text


@pytest.mark.asyncio
async def test_logout_clears_session(test_client: AsyncTestClient) -> None:
    """After logout, protected pages should redirect to login again."""
    await test_client.post("/logout", follow_redirects=False)

    response = await test_client.get("/week-menu", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_first_invited_account_claims_restored_recipes(
    anon_client: AsyncTestClient,
) -> None:
    """The first invited account should inherit restored placeholder-owned data."""
    legacy_user = await User.create(username="_legacy", email="")
    await Recipe.create(
        name="Legacy dish",
        description="Old recipe",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=legacy_user,
        creator=legacy_user,
        enabled=True,
    )

    user, password = await create_invited_user(
        username="firstowner", temporary_password="password1"
    )
    assert user is not None
    recipe = await Recipe.get(name="Legacy dish").select_related("owner")
    assert recipe.owner.id == user.id
    assert await User.get_by_username("_legacy") is None

    await anon_client.post(
        "/login", data={"username": "firstowner", "password": password}
    )
    # Must change password before using the app.
    blocked = await anon_client.get("/week-menu", follow_redirects=False)
    assert blocked.status_code == 302
    assert blocked.headers["location"] == "/profile/password"


@pytest.mark.asyncio
async def test_invite_reclaims_placeholder_username(
    anon_client: AsyncTestClient,
) -> None:
    """A restored placeholder username must not block inviting that username."""
    await User.create(username="erick", email="")

    user, password = await create_invited_user(
        username="erick", temporary_password="password1"
    )
    assert user.password_hash is not None
    assert await User.filter(username="erick").count() == 1

    await anon_client.post("/login", data={"username": "erick", "password": password})
    await anon_client.post(
        "/profile/password",
        data={
            "new_password": "password1",
            "new_password_confirm": "password1",
        },
    )
    protected = await anon_client.get("/week-menu", follow_redirects=False)
    assert protected.status_code == 200


@pytest.mark.asyncio
async def test_forced_password_change_flow(anon_client: AsyncTestClient) -> None:
    """Invited users must set a new password before accessing the app."""
    await register_user(
        anon_client,
        username="invitee",
        password="temp-pass-1",
        must_change_password=True,
    )

    blocked = await anon_client.get("/", follow_redirects=False)
    assert blocked.status_code == 302
    assert blocked.headers["location"] == "/profile/password"

    form = await anon_client.get("/profile/password")
    assert form.status_code == 200
    assert "Choose a new password" in form.text
    assert "current_password" not in form.text

    changed = await anon_client.post(
        "/profile/password",
        data={
            "new_password": "permanent-pass",
            "new_password_confirm": "permanent-pass",
        },
        follow_redirects=False,
    )
    assert changed.status_code == 302
    assert changed.headers["location"] == "/"

    user = await User.get_by_username("invitee")
    assert user is not None
    assert user.must_change_password is False
    assert verify_password("permanent-pass", user.password_hash) is True

    home = await anon_client.get("/", follow_redirects=False)
    assert home.status_code == 200


@pytest.mark.asyncio
async def test_change_password(test_client: AsyncTestClient) -> None:
    """Changing the password should require the correct current password."""
    wrong = await test_client.post(
        "/profile/password",
        data={
            "current_password": "not-the-password",
            "new_password": "brand-new-pass",
            "new_password_confirm": "brand-new-pass",
        },
    )
    assert "Current password is incorrect" in wrong.text

    ok = await test_client.post(
        "/profile/password",
        data={
            "current_password": DEFAULT_PASSWORD,
            "new_password": "brand-new-pass",
            "new_password_confirm": "brand-new-pass",
        },
    )
    assert "Password changed" in ok.text

    user = await User.get_by_username(DEFAULT_USERNAME)
    assert user is not None
    assert verify_password("brand-new-pass", user.password_hash) is True


@pytest.mark.asyncio
async def test_delete_account(test_client: AsyncTestClient) -> None:
    """Deleting the account should remove the user and end the session."""
    response = await test_client.post("/profile/delete", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"
    assert await User.get_by_username(DEFAULT_USERNAME) is None


@pytest.mark.asyncio
async def test_profile_settings_can_be_updated(test_client: AsyncTestClient) -> None:
    """Language and default servings should be saved from profile settings."""
    response = await test_client.post(
        "/profile/settings",
        data={"language": "🇳🇱 Nederlands", "servings": "5"},
    )
    assert response.status_code == 200
    assert "Settings updated." in response.text
    assert "🇳🇱 Nederlands" in response.text
    assert 'id="servings" name="servings" type="number" min="1"' in response.text
    assert 'value="5"' in response.text

    user = await User.get_by_username(DEFAULT_USERNAME)
    assert user is not None
    settings = await load_user_settings(user.id)
    assert settings["language"] == "🇳🇱 Nederlands"
    assert settings["servings"] == 5
