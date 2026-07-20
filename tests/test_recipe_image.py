"""Tests for recipe image URL validation and UI wiring."""

import pytest
from litestar.testing import AsyncTestClient

from src.auth import hash_password
from src.models import Recipe, User
from src.recipe_image import MAX_IMAGE_URL_LENGTH, parse_recipe_image_url


def test_empty_image_url_clears_value() -> None:
    """Blank input should clear the image URL."""
    assert parse_recipe_image_url("") == (True, None, None)
    assert parse_recipe_image_url("   ") == (True, None, None)
    assert parse_recipe_image_url(None) == (True, None, None)


def test_https_image_urls_are_accepted() -> None:
    """Common http(s) image URLs with allowed extensions should pass."""
    ok, value, error = parse_recipe_image_url(
        "https://cdn.example.com/food/pasta.jpg?w=800"
    )
    assert ok is True
    assert value == "https://cdn.example.com/food/pasta.jpg?w=800"
    assert error is None

    ok, value, error = parse_recipe_image_url("http://example.com/a.PNG")
    assert ok is True
    assert value == "http://example.com/a.PNG"
    assert error is None


def test_rejects_dangerous_schemes_and_svg() -> None:
    """Non-http schemes and SVG must be rejected."""
    for raw in (
        "javascript:alert(1)",
        "data:image/png;base64,abc",
        "file:///tmp/x.png",
        "https://example.com/pic.svg",
        "https://example.com/pic.svg?download=1",
    ):
        ok, value, error = parse_recipe_image_url(raw)
        assert ok is False
        assert value is None
        assert error


def test_rejects_missing_extension_credentials_and_controls() -> None:
    """Paths without an image extension, credentials, and control chars fail."""
    ok, _, error = parse_recipe_image_url("https://example.com/no-extension")
    assert ok is False
    assert error

    ok, _, error = parse_recipe_image_url("https://user:pass@example.com/a.jpg")
    assert ok is False
    assert error

    ok, _, error = parse_recipe_image_url("https://example.com/a.jpg\n")
    assert ok is False
    assert error


def test_rejects_oversized_urls() -> None:
    """URLs longer than the configured maximum should fail."""
    raw = "https://example.com/" + ("a" * MAX_IMAGE_URL_LENGTH) + ".jpg"
    ok, value, error = parse_recipe_image_url(raw)
    assert ok is False
    assert value is None
    assert error


@pytest.mark.asyncio
async def test_add_recipe_stores_valid_image_url(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Adding a recipe with a valid image URL should persist it."""
    image_url = "https://cdn.example.com/dishes/stew.webp"
    response = await test_client.post(
        "/recipes",
        data={
            "name": "__pytest_image_url__",
            "servings": "2",
            "description": "With image",
            "prep_time_minutes": "10",
            "cook_time_minutes": "20",
            "image_url": image_url,
        },
        follow_redirects=False,
    )

    assert response.status_code in {302, 303, 307, 308}
    recipe = await Recipe.filter(name="__pytest_image_url__").order_by("-id").first()
    assert recipe is not None
    assert recipe.image_url == image_url
    owner = await recipe.owner
    assert owner.id == default_user.id

    view = await test_client.get(f"/recipes/view/{recipe.id}")
    assert view.status_code == 200
    assert f'src="{image_url}"' in view.text
    assert 'class="recipe-image"' in view.text


@pytest.mark.asyncio
async def test_add_recipe_rejects_invalid_image_url(
    test_client: AsyncTestClient,
) -> None:
    """Invalid image URLs should block create and show a warning."""
    response = await test_client.post(
        "/recipes",
        data={
            "name": "__pytest_bad_image__",
            "servings": "2",
            "description": "Bad image",
            "image_url": "https://example.com/pic.svg",
        },
    )

    assert response.status_code == 200
    assert "svg" in response.text.lower() or "image url" in response.text.lower()
    assert await Recipe.filter(name="__pytest_bad_image__").exists() is False


@pytest.mark.asyncio
async def test_edit_image_url_set_and_clear(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Edit image endpoint should set and clear the URL."""
    recipe = await Recipe.create(
        name="Image edit",
        description="Edit me",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
    )
    image_url = "https://example.com/food.png"

    set_response = await test_client.post(
        f"/recipes/edit-image/{recipe.id}",
        data={"image_url": image_url},
    )
    assert set_response.status_code == 200
    assert f'src="{image_url}"' in set_response.text
    await recipe.refresh_from_db()
    assert recipe.image_url == image_url

    clear_response = await test_client.post(
        f"/recipes/edit-image/{recipe.id}",
        data={"image_url": ""},
    )
    assert clear_response.status_code == 200
    await recipe.refresh_from_db()
    assert recipe.image_url is None


@pytest.mark.asyncio
async def test_import_copies_image_url(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Importing a public recipe should copy its image URL."""
    other = await User.create(
        username="image_owner",
        email="image_owner@example.com",
        password_hash=hash_password("password1"),
    )
    image_url = "https://example.com/shared.jpg"
    source = await Recipe.create(
        name="Shared with image",
        description="Public",
        image_url=image_url,
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=other,
        creator=other,
        private=False,
        enabled=True,
    )

    response = await test_client.post(
        f"/recipes/{source.id}/import", follow_redirects=False
    )
    assert response.status_code == 302
    copy_id = int(response.headers["location"].rstrip("/").split("/")[-1])
    copy = await Recipe.get(id=copy_id).select_related("owner")
    assert copy.image_url == image_url
    owner = await copy.owner
    assert owner.id == default_user.id
