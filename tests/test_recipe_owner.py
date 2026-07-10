"""Tests for recipe owner lookup helpers."""

import pytest
from litestar.testing import AsyncTestClient

from src.models import User


@pytest.mark.asyncio
async def test_get_by_username_returns_matching_user(
    test_client: AsyncTestClient,
) -> None:
    """Looking up a username should return the matching user or None."""
    assert await User.get_by_username("does-not-exist") is None

    created = await User.create(username="solo", email="solo@example.com")
    found = await User.get_by_username("solo")
    assert found is not None
    assert found.id == created.id
