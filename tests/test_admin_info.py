"""Tests for the admin technical info page."""

import pytest
from litestar.testing import AsyncTestClient

from src.auth import hash_password
from src.models import User
from tests.conftest import DEFAULT_PASSWORD


@pytest.mark.asyncio
async def test_admin_info_page_shows_sqlite_backend_for_tests(
    anon_client: AsyncTestClient,
) -> None:
    """Admins should see technical info; the test DB backend is SQLite."""
    await User.create(
        username="admininfo",
        email="admininfo@example.com",
        password_hash=hash_password(DEFAULT_PASSWORD),
        is_admin=True,
    )
    await anon_client.post(
        "/login",
        data={"username": "admininfo", "password": DEFAULT_PASSWORD},
    )

    response = await anon_client.get("/admin/info")

    assert response.status_code == 200
    assert "Technical info" in response.text
    assert "SQLite" in response.text
    assert "PostgreSQL version" not in response.text


@pytest.mark.asyncio
async def test_admin_info_page_forbidden_for_non_admin(
    test_client: AsyncTestClient,
) -> None:
    """Non-admin users must not access the technical info page."""
    response = await test_client.get("/admin/info")
    assert response.status_code == 403
