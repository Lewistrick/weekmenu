"""Per-user weekly grocery list, stored in the database.

Weekly groceries are recurring staples a user buys every week, unrelated to the
week menu. They can be managed on a settings page and added to any grocery list
in one action.
"""

from __future__ import annotations

from typing import Any, TypedDict

from src.catalog import get_or_create_ingredient
from src.i18n.service import t
from src.models import Unit, WeeklyGrocery
from src.week_menu import GroceryItem, grocery_line_key, parse_grocery_quantity


class WeeklyGroceryRow(TypedDict):
    """A weekly grocery prepared for display in templates."""

    id: int
    ingredient_id: int
    name: str
    unit: str
    quantity: float


async def load_weekly_groceries(owner_id: int) -> list[WeeklyGroceryRow]:
    """Return a user's weekly groceries sorted alphabetically by name."""
    rows = await WeeklyGrocery.filter(owner_id=owner_id).select_related(
        "ingredient", "unit"
    )
    prepared = [
        WeeklyGroceryRow(
            id=row.id,
            ingredient_id=row.ingredient.id,
            name=row.ingredient.name,
            unit=row.unit.abbrev,
            quantity=row.quantity,
        )
        for row in rows
    ]
    return sorted(prepared, key=lambda row: row["name"].lower())


async def weekly_groceries_as_items(owner_id: int) -> list[GroceryItem]:
    """Return a user's weekly groceries shaped as grocery list items."""
    return [
        GroceryItem(
            ingredient_id=row["ingredient_id"],
            name=row["name"],
            unit=row["unit"],
            quantity=row["quantity"],
        )
        for row in await load_weekly_groceries(owner_id)
    ]


def weekly_groceries_missing_from_list(
    weekly_items: list[GroceryItem], current_items: list[GroceryItem]
) -> list[GroceryItem]:
    """Return weekly groceries that are not yet on the grocery list.

    A weekly grocery counts as present when the same ingredient and unit
    already appear as a line on the current grocery list.
    """
    current_keys = {
        grocery_line_key(item["ingredient_id"], item["unit"]) for item in current_items
    }
    return [
        item
        for item in weekly_items
        if grocery_line_key(item["ingredient_id"], item["unit"]) not in current_keys
    ]


async def _resolve_ingredient_and_unit(
    owner_id: int, name: Any, quantity_raw: Any, unit_abbrev: Any
) -> tuple[int, float, int, None] | tuple[None, None, None, str]:
    """Validate weekly grocery input and resolve ingredient/unit ids.

    Returns:
        On success ``(ingredient_id, quantity, unit_id, None)``; on failure
        ``(None, None, None, error_message)``.
    """
    clean_name = str(name or "").strip()
    if not clean_name:
        return None, None, None, t("message.weekly_groceries.ingredient_required")

    quantity = parse_grocery_quantity(quantity_raw)
    if quantity is None:
        return None, None, None, t("message.weekly_groceries.positive_amount")

    clean_unit = str(unit_abbrev or "").strip()
    if not clean_unit:
        return None, None, None, t("message.weekly_groceries.unit_required")
    unit = await Unit.find(clean_unit, owner_id=owner_id)
    if unit is None:
        return (
            None,
            None,
            None,
            t("message.weekly_groceries.unit_not_found", unit=clean_unit),
        )

    ingredient, _ = await get_or_create_ingredient(owner_id, clean_name)
    return ingredient.id, quantity, unit.id, None


async def add_weekly_grocery(
    owner_id: int, name: Any, quantity_raw: Any, unit_abbrev: Any
) -> tuple[bool, str]:
    """Create a weekly grocery for a user, rejecting duplicates.

    Args:
        owner_id: The user creating the weekly grocery.
        name: Ingredient name; created in the catalog when new.
        quantity_raw: Raw amount from the form.
        unit_abbrev: Unit abbreviation that must already exist for the user.

    Returns:
        A success flag and a message describing the outcome.
    """
    ingredient_id, quantity, unit_id, error = await _resolve_ingredient_and_unit(
        owner_id, name, quantity_raw, unit_abbrev
    )
    if error is not None:
        return False, error
    assert ingredient_id is not None and quantity is not None and unit_id is not None

    if await WeeklyGrocery.filter(
        owner_id=owner_id, ingredient_id=ingredient_id, unit_id=unit_id
    ).exists():
        return False, t("message.weekly_groceries.already_exists")

    await WeeklyGrocery.create(
        owner_id=owner_id,
        ingredient_id=ingredient_id,
        quantity=quantity,
        unit_id=unit_id,
    )
    return True, t("message.weekly_groceries.added")


async def update_weekly_grocery(
    owner_id: int,
    weekly_id: int,
    name: Any,
    quantity_raw: Any,
    unit_abbrev: Any,
) -> tuple[bool, str]:
    """Update an owned weekly grocery, rejecting duplicates.

    Returns:
        A success flag and a message describing the outcome.
    """
    row = await WeeklyGrocery.get_or_none(id=weekly_id, owner_id=owner_id)
    if row is None:
        return False, t("message.weekly_groceries.not_found")

    ingredient_id, quantity, unit_id, error = await _resolve_ingredient_and_unit(
        owner_id, name, quantity_raw, unit_abbrev
    )
    if error is not None:
        return False, error
    assert ingredient_id is not None and quantity is not None and unit_id is not None

    duplicate = (
        await WeeklyGrocery.filter(
            owner_id=owner_id, ingredient_id=ingredient_id, unit_id=unit_id
        )
        .exclude(id=weekly_id)
        .exists()
    )
    if duplicate:
        return False, t("message.weekly_groceries.already_exists")

    row.ingredient_id = ingredient_id
    row.quantity = quantity
    row.unit_id = unit_id
    await row.save()
    return True, t("message.weekly_groceries.updated")


async def delete_weekly_grocery(owner_id: int, weekly_id: int) -> bool:
    """Delete an owned weekly grocery.

    Returns:
        ``True`` when a weekly grocery was deleted, otherwise ``False``.
    """
    row = await WeeklyGrocery.get_or_none(id=weekly_id, owner_id=owner_id)
    if row is None:
        return False
    await row.delete()
    return True
