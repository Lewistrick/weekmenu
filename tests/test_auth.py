"""Tests for authentication and account management."""

import pytest
from litestar.testing import AsyncTestClient

from src.auth import hash_password, verify_password
from src.models import Recipe, User
from src.user_settings import load_user_settings
from tests.conftest import DEFAULT_PASSWORD, DEFAULT_USERNAME, register_user


def test_password_hash_roundtrip() -> None:
    """A hashed password should verify against the original and reject others."""
    hashed = hash_password("hunter2!")
    assert hashed != "hunter2!"
    assert verify_password("hunter2!", hashed) is True
    assert verify_password("wrong", hashed) is False
    assert verify_password("anything", None) is False


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


@pytest.mark.asyncio
async def test_register_creates_account_and_authenticates(
    anon_client: AsyncTestClient,
) -> None:
    """Registering should create a user and start an authenticated session."""
    await register_user(anon_client, username="alice", password="wonderland")

    assert await User.get_by_username("alice") is not None
    # The session cookie should now grant access to a protected page.
    protected = await anon_client.get("/week-menu", follow_redirects=False)
    assert protected.status_code == 200


@pytest.mark.asyncio
async def test_register_rejects_duplicate_username(
    anon_client: AsyncTestClient,
) -> None:
    """Registering an existing username should fail with an error."""
    await register_user(anon_client, username="bob", password="password1")

    response = await anon_client.post(
        "/register",
        data={
            "username": "bob",
            "password": "password2",
            "password_confirm": "password2",
            "email": "",
        },
    )

    assert response.status_code == 200
    assert "already taken" in response.text
    assert await User.filter(username="bob").count() == 1


@pytest.mark.asyncio
async def test_register_rejects_mismatched_passwords(
    anon_client: AsyncTestClient,
) -> None:
    """Mismatched password confirmation should be rejected."""
    response = await anon_client.post(
        "/register",
        data={
            "username": "carol",
            "password": "password1",
            "password_confirm": "password2",
            "email": "",
        },
    )

    assert response.status_code == 200
    assert "do not match" in response.text
    assert await User.get_by_username("carol") is None


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
async def test_first_account_backfills_existing_recipes(
    anon_client: AsyncTestClient,
) -> None:
    """The first registered account should inherit legacy password-less data."""
    legacy_user = await User.create(username="legacy", email="old@example.com")
    await Recipe.create(
        name="Legacy dish",
        description="Old recipe",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=legacy_user,
        enabled=True,
    )

    await register_user(anon_client, username="firstowner", password="password1")

    new_user = await User.get_by_username("firstowner")
    assert new_user is not None
    recipe = await Recipe.get(name="Legacy dish")
    assert recipe.owner_id == new_user.id
    # The password-less legacy account should be removed.
    assert await User.get_by_username("legacy") is None


@pytest.mark.asyncio
async def test_register_with_legacy_username_succeeds(
    anon_client: AsyncTestClient,
) -> None:
    """A password-less legacy account must not block registering that username."""
    await User.create(username="erick", email="old@example.com")

    await register_user(anon_client, username="erick", password="password1")

    protected = await anon_client.get("/week-menu", follow_redirects=False)
    assert protected.status_code == 200

    users = await User.filter(username="erick").all()
    assert len(users) == 1
    assert users[0].password_hash is not None


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
    assert response.headers["location"] == "/register"
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
    settings = load_user_settings(user.id)
    assert settings["language"] == "🇳🇱 Nederlands"
    assert settings["servings"] == 5
