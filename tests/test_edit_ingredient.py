"""Tests for adding and editing recipe ingredients."""

import pytest
from litestar.testing import AsyncTestClient
from tortoise import Tortoise

from src.app import app
from src.models import Ingredient, Recipe, RecipeIngredient, Unit

TEST_DB_CONFIG = {
    "connections": {"default": "sqlite://:memory:"},
    "apps": {
        "models": {
            "models": ["src.models", "aerich.models"],
            "default_connection": "default",
        }
    },
}


@pytest.fixture
async def test_client(monkeypatch: pytest.MonkeyPatch) -> AsyncTestClient:
    """Provide a test client backed by an in-memory database."""

    async def init_test_db() -> None:
        await Tortoise.init(config=TEST_DB_CONFIG)
        await Tortoise.generate_schemas(safe=True)

    monkeypatch.setattr("src.app.init_db", init_test_db)

    async with AsyncTestClient(app=app) as client:
        yield client


@pytest.fixture
async def recipe_with_ingredient(
    test_client: AsyncTestClient,
) -> tuple[Recipe, RecipeIngredient]:
    """Create a recipe with one ingredient line for edit tests."""
    recipe = await Recipe.create(
        name="Test Soup",
        description="Tasty",
        prep_time_minutes=10,
        cook_time_minutes=20,
        servings=4,
    )
    ingredient = await Ingredient.create(name="potatoes")
    unit = await Unit.create(abbrev="g", single="gram", plural="grams")
    recipe_ingredient = await RecipeIngredient.create(
        recipe=recipe,
        ingredient=ingredient,
        quantity=200.0,
        unit=unit,
    )
    return recipe, recipe_ingredient


@pytest.fixture
async def recipe(
    test_client: AsyncTestClient,
) -> Recipe:
    """Create a recipe without ingredients for add tests."""
    return await Recipe.create(
        name="Empty Soup",
        description="Tasty",
        prep_time_minutes=10,
        cook_time_minutes=20,
        servings=4,
    )


@pytest.mark.asyncio
async def test_edit_ingredient_updates_quantity_and_unit(
    test_client: AsyncTestClient,
    recipe_with_ingredient: tuple[Recipe, RecipeIngredient],
) -> None:
    """Saving the edit form should persist quantity and unit changes."""
    recipe, recipe_ingredient = recipe_with_ingredient
    await Unit.create(abbrev="ml", single="milliliter", plural="milliliters")

    response = await test_client.put(
        f"/recipes/{recipe.id}/ingredients/{recipe_ingredient.id}/edit",
        data={"quantity": "350", "unit": "ml", "ingredient": "potatoes"},
    )

    assert response.status_code == 200
    assert "350" in response.text
    assert "ml" in response.text
    assert "potatoes" in response.text

    await recipe_ingredient.refresh_from_db()
    await recipe_ingredient.fetch_related("unit")
    assert recipe_ingredient.quantity == 350.0
    assert recipe_ingredient.unit.abbrev == "ml"


@pytest.mark.asyncio
async def test_ingredient_editor_uses_recipe_ingredient_id(
    test_client: AsyncTestClient,
    recipe_with_ingredient: tuple[Recipe, RecipeIngredient],
) -> None:
    """The edit form should target the recipe-ingredient row id, not the ingredient id."""
    recipe, recipe_ingredient = recipe_with_ingredient
    ingredient = await recipe_ingredient.ingredient

    response = await test_client.get(
        f"/recipes/{recipe.id}/ingredients/{recipe_ingredient.id}/edit",
    )

    assert response.status_code == 200
    assert (
        f"/recipes/{recipe.id}/ingredients/{recipe_ingredient.id}/edit" in response.text
    )
    assert f"#edit-ingredient-{recipe_ingredient.id}" in response.text
    assert f"/ingredients/{ingredient.id}/edit" not in response.text


@pytest.mark.asyncio
async def test_add_ingredient_creates_recipe_ingredient(
    test_client: AsyncTestClient,
    recipe: Recipe,
) -> None:
    """Submitting the add form should append a new ingredient line to the recipe."""
    await Unit.create(abbrev="g", single="gram", plural="grams")

    response = await test_client.post(
        f"/recipes/{recipe.id}/ingredients/add",
        data={"quantity": "100", "unit": "g", "ingredient": "carrots"},
    )

    assert response.status_code == 200
    assert "100" in response.text
    assert "g" in response.text
    assert "carrots" in response.text
    assert "Ingredient added" in response.text

    recipe_ingredients = await RecipeIngredient.filter(recipe=recipe.id).select_related(
        "ingredient", "unit"
    )
    assert len(recipe_ingredients) == 1
    assert recipe_ingredients[0].quantity == 100.0
    assert recipe_ingredients[0].ingredient.name == "carrots"
    assert recipe_ingredients[0].unit.abbrev == "g"


@pytest.mark.asyncio
async def test_add_ingredient_finds_unit_by_name(
    test_client: AsyncTestClient,
    recipe: Recipe,
) -> None:
    """Unit lookup should accept abbreviations, singular, and plural forms."""
    await Unit.create(abbrev="g", single="gram", plural="grams")

    response = await test_client.post(
        f"/recipes/{recipe.id}/ingredients/add",
        data={"quantity": "50", "unit": "grams", "ingredient": "onions"},
    )

    assert response.status_code == 200
    assert "Ingredient added" in response.text

    recipe_ingredient = (
        await RecipeIngredient.filter(recipe=recipe.id)
        .select_related("unit", "ingredient")
        .first()
    )
    assert recipe_ingredient is not None
    assert recipe_ingredient.unit.abbrev == "g"
    assert recipe_ingredient.ingredient.name == "onions"


@pytest.mark.asyncio
async def test_add_ingredient_form_targets_recipe_ingredient_list(
    test_client: AsyncTestClient,
    recipe: Recipe,
) -> None:
    """The add form should refresh the ingredient list after submit."""
    response = await test_client.get(f"/recipes/{recipe.id}/ingredients/add")

    assert response.status_code == 200
    assert f"/recipes/{recipe.id}/ingredients/add" in response.text
    assert 'hx-target="#recipe-ingredients"' in response.text
    assert 'id="add-ingredient-form"' not in response.text
