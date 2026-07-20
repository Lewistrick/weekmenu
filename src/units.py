"""Per-user unit catalog helpers."""

from collections import defaultdict
from typing import TypedDict

from src.i18n.service import t
from src.models import GroceryListItem, RecipeIngredient, Unit, WeeklyGrocery


class UnitRecipeUsage(TypedDict):
    """One recipe that uses a unit, plus the matching ingredient names."""

    recipe_id: int
    recipe_name: str
    ingredient_names: list[str]


class UnitRow(TypedDict):
    """One unit prepared for display on the management page."""

    id: int
    abbrev: str
    single: str
    plural: str
    incomplete: bool
    recipe_usages: list[UnitRecipeUsage]
    weekly_grocery_names: list[str]
    grocery_list_names: list[str]


def _normalize_text(value: object) -> str:
    """Return trimmed text from form input."""
    return str(value or "").strip()


def unit_is_complete(abbrev: str, single: str, plural: str) -> bool:
    """Return whether a unit has abbreviation, singular, and plural labels."""
    return bool(abbrev.strip() and single.strip() and plural.strip())


def _recipe_usages_for_unit(
    unit_id: int,
    usages_by_unit: dict[int, dict[int, set[str]]],
    recipe_names: dict[tuple[int, int], str],
) -> list[UnitRecipeUsage]:
    """Build sorted recipe usage rows for one unit."""
    return [
        UnitRecipeUsage(
            recipe_id=recipe_id,
            recipe_name=recipe_names[(unit_id, recipe_id)],
            ingredient_names=sorted(ingredient_names),
        )
        for recipe_id, ingredient_names in sorted(
            (
                (recipe_id, ingredient_names)
                for recipe_id, ingredient_names in usages_by_unit[unit_id].items()
            ),
            key=lambda usage: (
                recipe_names[(unit_id, usage[0])].lower(),
                usage[0],
            ),
        )
    ]


async def load_units(owner_id: int) -> list[UnitRow]:
    """Return a user's units sorted by abbreviation."""
    rows = await Unit.filter(owner_id=owner_id).order_by("abbrev")
    unit_ids = [row.id for row in rows]
    usages_by_unit: dict[int, dict[int, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    recipe_names: dict[tuple[int, int], str] = {}
    weekly_by_unit: dict[int, set[str]] = defaultdict(set)
    grocery_list_by_unit: dict[int, set[str]] = defaultdict(set)

    if unit_ids:
        recipe_ingredients = await RecipeIngredient.filter(
            recipe__owner_id=owner_id,
            unit_id__in=unit_ids,
        ).values("unit_id", "recipe_id", "recipe__name", "ingredient__name")
        for recipe_ingredient in recipe_ingredients:
            unit_id = int(recipe_ingredient["unit_id"])
            recipe_id = int(recipe_ingredient["recipe_id"])
            usages_by_unit[unit_id][recipe_id].add(
                str(recipe_ingredient["ingredient__name"])
            )
            recipe_names[(unit_id, recipe_id)] = str(recipe_ingredient["recipe__name"])

        weekly_rows = await WeeklyGrocery.filter(
            owner_id=owner_id,
            unit_id__in=unit_ids,
        ).values("unit_id", "ingredient__name")
        for weekly_row in weekly_rows:
            weekly_by_unit[int(weekly_row["unit_id"])].add(
                str(weekly_row["ingredient__name"])
            )

        grocery_rows = await GroceryListItem.filter(
            user_id=owner_id,
            unit_id__in=unit_ids,
        ).values("unit_id", "ingredient__name")
        for grocery_row in grocery_rows:
            grocery_list_by_unit[int(grocery_row["unit_id"])].add(
                str(grocery_row["ingredient__name"])
            )

    return [
        UnitRow(
            id=row.id,
            abbrev=row.abbrev,
            single=row.single or "",
            plural=row.plural or "",
            incomplete=not unit_is_complete(
                row.abbrev, row.single or "", row.plural or ""
            ),
            recipe_usages=_recipe_usages_for_unit(row.id, usages_by_unit, recipe_names),
            weekly_grocery_names=sorted(weekly_by_unit[row.id]),
            grocery_list_names=sorted(grocery_list_by_unit[row.id]),
        )
        for row in rows
    ]


async def unit_is_in_use(*, owner_id: int, unit_id: int) -> bool:
    """Return whether a unit is referenced by this user's data.

    We scope checks to ``owner_id`` so another account's catalog usage cannot
    block deletion of the currently managed unit.
    """
    if await RecipeIngredient.filter(
        unit_id=unit_id, recipe__owner_id=owner_id
    ).exists():
        return True
    if await WeeklyGrocery.filter(owner_id=owner_id, unit_id=unit_id).exists():
        return True
    return await GroceryListItem.filter(user_id=owner_id, unit_id=unit_id).exists()


async def add_unit(
    owner_id: int, abbrev_raw: object, single_raw: object, plural_raw: object
) -> tuple[bool, str]:
    """Create a unit for one user.

    Returns:
        A success flag and user-facing message.
    """
    abbrev = _normalize_text(abbrev_raw)
    single = _normalize_text(single_raw) or None
    plural = _normalize_text(plural_raw) or None
    if not abbrev:
        return False, t("message.units.abbrev_required")
    await Unit.create(owner_id=owner_id, abbrev=abbrev, single=single, plural=plural)
    return True, t("message.units.added")


async def update_unit(
    owner_id: int,
    unit_id: int,
    abbrev_raw: object,
    single_raw: object,
    plural_raw: object,
) -> tuple[bool, str]:
    """Update one owned unit.

    Returns:
        A success flag and user-facing message.
    """
    unit = await Unit.get_or_none(id=unit_id, owner_id=owner_id)
    if unit is None:
        return False, t("message.units.not_found")
    abbrev = _normalize_text(abbrev_raw)
    single = _normalize_text(single_raw) or None
    plural = _normalize_text(plural_raw) or None
    if not abbrev:
        return False, t("message.units.abbrev_required")
    await Unit.filter(id=unit_id, owner_id=owner_id).update(
        abbrev=abbrev,
        single=single,
        plural=plural,
    )
    return True, t("message.units.updated")


async def delete_unit(owner_id: int, unit_id: int) -> tuple[bool, str]:
    """Delete one owned unit when it is not in use.

    Returns:
        A success flag and user-facing message.
    """
    unit = await Unit.get_or_none(id=unit_id, owner_id=owner_id)
    if unit is None:
        return False, t("message.units.not_found")
    if await unit_is_in_use(owner_id=owner_id, unit_id=unit.id):
        return (
            False,
            t("message.units.in_use", abbrev=unit.abbrev),
        )
    await unit.delete()
    return True, t("message.units.deleted")
