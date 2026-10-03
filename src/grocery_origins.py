"""Where each grocery ingredient came from (week menu, weekly groceries, hand)."""

from collections import defaultdict

from src.grocery import IngredientOrigin, compute_ingredient_origins
from src.models import Recipe, RecipeIngredient
from src.plan_store import load_week_menu
from src.weekly_groceries import weekly_groceries_as_items


async def load_ingredient_origins(
    user_id: int, default_servings: int
) -> dict[int, IngredientOrigin]:
    """Reconstruct where each grocery ingredient came from.

    Origins are not persisted; they are recomputed from the current week menu
    (recipe names) and the weekly groceries. Ingredients matching neither
    source are treated as manually added by the caller.

    Args:
        user_id: Owner of the week menu and weekly groceries.
        default_servings: The user's default servings, for empty menu slots.

    Returns:
        A mapping of ingredient id to its :class:`IngredientOrigin`.
    """
    menu = await load_week_menu(user_id, default_servings=default_servings)
    recipe_ids = [
        slot["recipe_id"] for slot in menu.values() if slot["recipe_id"] is not None
    ]
    recipe_names: dict[int, str] = {}
    if recipe_ids:
        recipe_names = {
            recipe.id: recipe.name for recipe in await Recipe.filter(id__in=recipe_ids)
        }

    recipe_ingredient_ids: dict[int, set[int]] = defaultdict(set)
    if recipe_ids:
        recipe_ingredients = await RecipeIngredient.filter(
            recipe_id__in=recipe_ids
        ).select_related("recipe", "ingredient")
        for recipe_ingredient in recipe_ingredients:
            recipe_ingredient_ids[recipe_ingredient.recipe.id].add(
                recipe_ingredient.ingredient.id
            )

    weekly_ingredient_ids = {
        item["ingredient_id"] for item in await weekly_groceries_as_items(user_id)
    }
    return compute_ingredient_origins(
        dict(recipe_ingredient_ids), recipe_names, weekly_ingredient_ids
    )
