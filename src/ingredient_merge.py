"""Merge duplicate ingredients that differ only by name."""

from dataclasses import dataclass

from loguru import logger

from src.i18n.service import t
from src.models import (
    GroceryListItem,
    Ingredient,
    RecipeIngredient,
    Unit,
    UserIngredientShop,
    WeeklyGrocery,
)
from src.shops import load_ingredient_recipe_counts


@dataclass(frozen=True)
class IngredientOption:
    """One ingredient selectable on the merge page."""

    id: int
    name: str
    recipe_count: int


@dataclass(frozen=True)
class IngredientMergeResult:
    """Outcome of merging one ingredient into another."""

    ok: bool
    error_message: str = ""
    source_name: str = ""
    target_name: str = ""
    recipe_ids: tuple[int, ...] = ()


async def load_ingredient_options(owner_id: int) -> list[IngredientOption]:
    """Return all owned ingredients for the merge form.

    Args:
        owner_id: The logged-in user's id.

    Returns:
        Ingredients sorted by name with recipe usage counts.
    """
    ingredients = await Ingredient.filter(owner_id=owner_id).order_by("name")
    recipe_counts = await load_ingredient_recipe_counts(owner_id)
    return [
        IngredientOption(
            id=ingredient.id,
            name=ingredient.name,
            recipe_count=recipe_counts.get(ingredient.id, 0),
        )
        for ingredient in ingredients
    ]


async def search_ingredient_options(
    owner_id: int,
    query: str,
    *,
    limit: int = 10,
) -> list[IngredientOption]:
    """Return ingredients whose names match a search query.

    Args:
        owner_id: The logged-in user's id.
        query: Substring to match against ingredient names.
        limit: Maximum number of results to return.

    Returns:
        Matching ingredients sorted by name.
    """
    ingredients = await load_ingredient_options(owner_id)
    normalized = query.strip().casefold()
    if not normalized:
        return ingredients[:limit]
    return [item for item in ingredients if normalized in item.name.casefold()][:limit]


async def log_ingredient_usages(
    owner_id: int,
    ingredient_id: int,
    role: str,
) -> None:
    """Log recipe usages for one ingredient (debug helper).

    Args:
        owner_id: The logged-in user's id.
        ingredient_id: Ingredient to inspect.
        role: Label for log lines (for example ``source`` or ``target``).
    """
    ingredient = await Ingredient.get_or_none(id=ingredient_id, owner_id=owner_id)
    if ingredient is None:
        logger.debug(
            "Merge preview {} ingredient id={} - (not found)", role, ingredient_id
        )
        return

    logger.debug(
        "Merge preview {} ingredient {} (id={})",
        role,
        ingredient.name,
        ingredient.id,
    )
    rows = await RecipeIngredient.filter(
        ingredient_id=ingredient.id,
        recipe__owner_id=owner_id,
    ).select_related("recipe", "unit")
    if not rows:
        logger.debug("{} - (no recipes)", ingredient.name)
    for row in rows:
        unit = row.unit
        unit_name = _unit_name(unit) if unit else "?"
        logger.debug(
            "{} / {} - /recipes/view/{} - {}",
            ingredient.name,
            unit_name,
            row.recipe.id,
            row.recipe.name,
        )


def _unit_name(unit: Unit) -> str:
    """Return a display label for a unit."""
    if unit.single:
        return f"{unit.single} ({unit.abbrev})"
    return unit.abbrev


async def _merge_recipe_ingredients(
    owner_id: int,
    source_ingredient_id: int,
    target_ingredient_id: int,
) -> list[int]:
    """Reassign source recipe lines to the target ingredient."""
    edited_recipe_ids: set[int] = set()
    source_rows = await RecipeIngredient.filter(
        ingredient_id=source_ingredient_id,
        recipe__owner_id=owner_id,
    ).select_related("recipe", "unit")
    for row in source_rows:
        recipe_id = row.recipe.id
        unit = row.unit
        assert unit is not None
        matching_unit = await RecipeIngredient.get_or_none(
            recipe_id=recipe_id,
            ingredient_id=target_ingredient_id,
            unit_id=unit.id,
        )
        if matching_unit is not None:
            matching_unit.quantity += row.quantity
            await matching_unit.save()
            await row.delete()
        else:
            await RecipeIngredient.filter(id=row.id).update(
                ingredient_id=target_ingredient_id
            )
        edited_recipe_ids.add(recipe_id)
    return sorted(edited_recipe_ids)


async def _merge_weekly_groceries(
    owner_id: int,
    source_ingredient_id: int,
    target_ingredient_id: int,
) -> None:
    """Reassign source weekly grocery lines to the target ingredient."""
    source_rows = await WeeklyGrocery.filter(
        owner_id=owner_id,
        ingredient_id=source_ingredient_id,
    ).select_related("unit")
    for row in source_rows:
        unit = row.unit
        assert unit is not None
        matching_unit = await WeeklyGrocery.get_or_none(
            owner_id=owner_id,
            ingredient_id=target_ingredient_id,
            unit_id=unit.id,
        )
        if matching_unit is not None:
            matching_unit.quantity += row.quantity
            await matching_unit.save()
            await row.delete()
        else:
            await WeeklyGrocery.filter(id=row.id).update(
                ingredient_id=target_ingredient_id
            )


async def _merge_grocery_list_items(
    owner_id: int,
    source_ingredient_id: int,
    target_ingredient_id: int,
) -> None:
    """Reassign source grocery list lines to the target ingredient."""
    source_rows = await GroceryListItem.filter(
        user_id=owner_id,
        ingredient_id=source_ingredient_id,
    ).select_related("unit")
    for row in source_rows:
        unit = row.unit
        assert unit is not None
        matching_unit = await GroceryListItem.get_or_none(
            user_id=owner_id,
            ingredient_id=target_ingredient_id,
            unit_id=unit.id,
        )
        if matching_unit is not None:
            matching_unit.quantity += row.quantity
            await matching_unit.save()
            await row.delete()
        else:
            await GroceryListItem.filter(id=row.id).update(
                ingredient_id=target_ingredient_id
            )


async def _merge_shop_assignments(
    owner_id: int,
    source_ingredient_id: int,
    target_ingredient_id: int,
) -> None:
    """Keep the target shop assignment and remove the source mapping."""
    source_mapping = await UserIngredientShop.get_or_none(
        user_id=owner_id,
        ingredient_id=source_ingredient_id,
    )
    if source_mapping is None:
        return

    target_mapping = await UserIngredientShop.get_or_none(
        user_id=owner_id,
        ingredient_id=target_ingredient_id,
    )
    if target_mapping is None:
        await UserIngredientShop.filter(id=source_mapping.id).update(
            ingredient_id=target_ingredient_id
        )
        return

    await source_mapping.delete()


async def merge_ingredients(
    owner_id: int,
    source_ingredient_id: int,
    target_ingredient_id: int,
) -> IngredientMergeResult:
    """Merge one ingredient into another and delete the source ingredient.

    The target ingredient keeps its name. Recipe lines with the same unit are
    combined by summing quantities. Lines with different units remain separate.

    Args:
        owner_id: The logged-in user's id.
        source_ingredient_id: Ingredient to remove after reassignment.
        target_ingredient_id: Ingredient to keep.

    Returns:
        Structured merge result with edited recipe ids on success.
    """
    if source_ingredient_id == target_ingredient_id:
        return IngredientMergeResult(
            ok=False,
            error_message=t("message.ingredient_merge.same_ingredient"),
        )

    source = await Ingredient.get_or_none(id=source_ingredient_id, owner_id=owner_id)
    target = await Ingredient.get_or_none(id=target_ingredient_id, owner_id=owner_id)
    if source is None or target is None:
        return IngredientMergeResult(
            ok=False,
            error_message=t("message.ingredient_merge.not_found"),
        )

    recipe_ids = await _merge_recipe_ingredients(
        owner_id,
        source_ingredient_id,
        target_ingredient_id,
    )
    await _merge_weekly_groceries(owner_id, source_ingredient_id, target_ingredient_id)
    await _merge_grocery_list_items(
        owner_id, source_ingredient_id, target_ingredient_id
    )
    await _merge_shop_assignments(owner_id, source_ingredient_id, target_ingredient_id)

    await source.delete()

    return IngredientMergeResult(
        ok=True,
        source_name=source.name,
        target_name=target.name,
        recipe_ids=tuple(recipe_ids),
    )
