"""Tests for per-user recipe visibility and week menu isolation."""

import pytest
from litestar.testing import AsyncTestClient

from src.auth import hash_password
from src.models import Recipe, User
from tests.conftest import register_user


async def _make_user(username: str) -> User:
    """Create an activated (password-bearing) user."""
    return await User.create(
        username=username, email="", password_hash=hash_password("password1")
    )


async def _make_recipe(owner: User, name: str, *, private: bool) -> Recipe:
    """Create a recipe owned by ``owner`` with the given privacy."""
    return await Recipe.create(
        name=name,
        description="Description",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=owner,
        creator=owner,
        private=private,
        enabled=True,
    )


@pytest.mark.asyncio
async def test_search_defaults_to_own_recipes_only(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Recipe.search excludes other users' public recipes unless opted in."""
    other = await _make_user("bob")
    mine = await _make_recipe(default_user, "My Private Dish", private=True)
    others_public = await _make_recipe(other, "Shared Dish", private=False)
    others_private = await _make_recipe(other, "Secret Dish", private=True)

    own_only = await Recipe.search("Dish", viewer_id=default_user.id)
    own_only_ids = {recipe.id for recipe in own_only}
    assert mine.id in own_only_ids
    assert others_public.id not in own_only_ids
    assert others_private.id not in own_only_ids

    with_public = await Recipe.search(
        "Dish", viewer_id=default_user.id, include_public=True
    )
    with_public_ids = {recipe.id for recipe in with_public}
    assert mine.id in with_public_ids
    assert others_public.id in with_public_ids
    assert others_private.id not in with_public_ids


@pytest.mark.asyncio
async def test_view_other_users_private_recipe_is_hidden(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Viewing another user's private recipe returns 404; a public one is visible."""
    other = await _make_user("bob")
    private_recipe = await _make_recipe(other, "Secret Dish", private=True)
    public_recipe = await _make_recipe(other, "Shared Dish", private=False)

    hidden = await test_client.get(f"/recipes/view/{private_recipe.id}")
    assert hidden.status_code == 404

    visible = await test_client.get(f"/recipes/view/{public_recipe.id}")
    assert visible.status_code == 200
    assert "Shared Dish" in visible.text


@pytest.mark.asyncio
async def test_cannot_edit_or_delete_other_users_recipe(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A user cannot edit or delete a recipe they do not own, even public ones."""
    other = await _make_user("bob")
    public_recipe = await _make_recipe(other, "Shared Dish", private=False)

    edit_page = await test_client.get(f"/recipes/edit/{public_recipe.id}")
    assert edit_page.status_code == 404

    deleted = await test_client.delete(f"/recipes/{public_recipe.id}")
    assert deleted.status_code == 404
    assert await Recipe.get_or_none(id=public_recipe.id) is not None


@pytest.mark.asyncio
async def test_search_endpoint_hides_other_users_private_recipe(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The search endpoint must not reveal another user's private recipe."""
    other = await _make_user("bob")
    await _make_recipe(other, "Secret Dish", private=True)

    response = await test_client.get(
        "/recipes/search-recipe", params={"search": "Secret Dish"}
    )

    assert response.status_code == 200
    assert "Secret Dish" not in response.text


@pytest.mark.asyncio
async def test_search_endpoint_can_include_public_recipes(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The search endpoint should include public recipes only when opted in."""
    other = await _make_user("bob")
    await _make_recipe(other, "Shared Dish", private=False)

    hidden = await test_client.get(
        "/recipes/search-recipe", params={"search": "Shared Dish"}
    )
    assert hidden.status_code == 200
    assert "Shared Dish" not in hidden.text

    visible = await test_client.get(
        "/recipes/search-recipe",
        params={"search": "Shared Dish", "include_public": "on"},
    )
    assert visible.status_code == 200
    assert "Shared Dish" in visible.text


@pytest.mark.asyncio
async def test_import_public_recipe_creates_private_copy_with_creator(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Importing a public recipe copies it privately and keeps creator attribution."""
    other = await _make_user("bob")
    source = await _make_recipe(other, "Shared Dish", private=False)

    response = await test_client.post(
        f"/recipes/{source.id}/import", follow_redirects=False
    )
    assert response.status_code == 302
    copy_id = int(response.headers["location"].rstrip("/").split("/")[-1])

    copy = await Recipe.get(id=copy_id)
    assert copy.owner_id == default_user.id
    assert copy.private is True
    assert copy.imported_from_id == source.id
    assert copy.creator_id == other.id

    page = await test_client.get(f"/recipes/view/{copy_id}")
    assert page.status_code == 200
    assert "Created by" in page.text
    assert other.username in page.text


@pytest.mark.asyncio
async def test_import_blocks_duplicate_copies(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Importing the same public recipe twice should be rejected."""
    other = await _make_user("bob")
    source = await _make_recipe(other, "Shared Dish", private=False)

    first = await test_client.post(
        f"/recipes/{source.id}/import", follow_redirects=False
    )
    assert first.status_code == 302

    second = await test_client.post(f"/recipes/{source.id}/import")
    assert second.status_code == 200
    assert "already imported" in second.text.lower()
    assert (
        await Recipe.filter(
            owner_id=default_user.id, imported_from_id=source.id
        ).count()
        == 1
    )


@pytest.mark.asyncio
async def test_week_menu_is_not_shared_between_users(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """One user's week menu must not appear for the next account on the same client."""
    my_recipe = await _make_recipe(default_user, "Erick Dinner", private=True)

    assigned = await test_client.post(f"/week-menu/monday/recipe/{my_recipe.id}")
    assert assigned.status_code == 200
    mine = await test_client.get("/week-menu")
    assert "Erick Dinner" in mine.text

    # Switch accounts on the same client/session.
    await test_client.post("/logout")
    await register_user(test_client, username="lewistrick", password="password1")

    theirs = await test_client.get("/week-menu")
    assert theirs.status_code == 200
    assert "Erick Dinner" not in theirs.text
