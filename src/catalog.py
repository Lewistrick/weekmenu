"""Per-user catalog helpers: default units and recipe import remapping."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from src.models import (
    Ingredient,
    Recipe,
    RecipeIngredient,
    RecipeTag,
    Tag,
    TagCategory,
    Unit,
)

if TYPE_CHECKING:
    from src.models import User

DEFAULT_UNITS: tuple[tuple[str, str | None, str | None], ...] = (
    ("g", "gram", "grams"),
    ("kg", "kilo", "kilo"),
    ("ml", "milliliter", "milliliter"),
    ("l", "liter", "liter"),
    ("el", "eetlepel", "eetlepels"),
    ("tl", "theelepel", "theelepels"),
    ("st", "stuk", "stuks"),
)


async def seed_default_units(user: User) -> int:
    """Create the default unit set for a user when they have none yet.

    Args:
        user: The account to seed units for.

    Returns:
        The number of units created.
    """
    if await Unit.filter(owner_id=user.id).exists():
        return 0

    created = 0
    for abbrev, single, plural in DEFAULT_UNITS:
        _, was_created = await Unit.get_or_create(
            owner_id=user.id,
            abbrev=abbrev,
            defaults={"single": single, "plural": plural},
        )
        if was_created:
            created += 1

    if created:
        logger.info(f"Seeded {created} default units for user: {user.username}")
    return created


async def get_or_create_ingredient(owner_id: int, name: str) -> tuple[Ingredient, bool]:
    """Return an ingredient owned by ``owner_id``, creating it when missing."""
    normalized = name.strip()
    existing = await Ingredient.filter(owner_id=owner_id, name=normalized).first()
    if existing is not None:
        return existing, False
    return await Ingredient.create(owner_id=owner_id, name=normalized), True


async def get_or_create_tag_category(
    owner_id: int, name: str
) -> tuple[TagCategory, bool]:
    """Return a tag category owned by ``owner_id``, creating it when missing."""
    normalized = name.strip()
    existing = await TagCategory.filter(owner_id=owner_id, name=normalized).first()
    if existing is not None:
        return existing, False
    return await TagCategory.create(owner_id=owner_id, name=normalized), True


async def get_or_create_tag(
    owner_id: int, name: str, category: TagCategory
) -> tuple[Tag, bool]:
    """Return a tag owned by ``owner_id`` in ``category``, creating it when missing."""
    normalized = name.strip()
    existing = await Tag.filter(
        owner_id=owner_id, category_id=category.id, name=normalized
    ).first()
    if existing is not None:
        return existing, False
    return await Tag.create(owner_id=owner_id, name=normalized, category=category), True


async def copy_recipe_catalog(
    source: Recipe, target_owner_id: int, copy: Recipe
) -> None:
    """Copy a recipe's ingredients and tags into another user's catalog.

    Args:
        source: The public recipe being imported.
        target_owner_id: The importer's user id.
        copy: The newly created private recipe copy.
    """
    source_ingredients = await RecipeIngredient.filter(
        recipe_id=source.id
    ).select_related("ingredient", "unit")
    for recipe_ingredient in source_ingredients:
        ingredient, _ = await get_or_create_ingredient(
            target_owner_id, recipe_ingredient.ingredient.name
        )
        unit = await Unit.find(recipe_ingredient.unit.abbrev, owner_id=target_owner_id)
        if unit is None:
            unit = await Unit.create(
                owner_id=target_owner_id,
                abbrev=recipe_ingredient.unit.abbrev,
                single=recipe_ingredient.unit.single,
                plural=recipe_ingredient.unit.plural,
            )
        await RecipeIngredient.create(
            recipe=copy,
            ingredient=ingredient,
            quantity=recipe_ingredient.quantity,
            unit=unit,
        )

    source_tags = await RecipeTag.filter(recipe_id=source.id).select_related(
        "tag", "tag__category"
    )
    for recipe_tag in source_tags:
        category, _ = await get_or_create_tag_category(
            target_owner_id, recipe_tag.tag.category.name
        )
        tag, _ = await get_or_create_tag(target_owner_id, recipe_tag.tag.name, category)
        await RecipeTag.create(recipe=copy, tag=tag)
