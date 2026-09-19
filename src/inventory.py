"""Per-user kitchen inventory, stored in the database.

Inventory items are amounts of an ingredient (in one unit) a user has at home.
There is at most one item per ingredient/unit combination; adding or editing an
item into an existing combination merges the two by adding their amounts.

How inventory interacts with the grocery list (reserving stock for lines on the
already-have list) lives in :mod:`src.plan_store`.
"""

from datetime import datetime
from typing import Any, TypedDict

from src.catalog import get_or_create_ingredient
from src.i18n.service import t
from src.models import InventoryItem, Unit

INVENTORY_SORT_UPDATED_DESC = "updated_desc"
INVENTORY_SORT_UPDATED_ASC = "updated_asc"
INVENTORY_SORT_NAME = "name"
INVENTORY_SORTS = (
    INVENTORY_SORT_UPDATED_DESC,
    INVENTORY_SORT_UPDATED_ASC,
    INVENTORY_SORT_NAME,
)


class InventoryRow(TypedDict):
    """An inventory item prepared for display in templates."""

    id: int
    ingredient_id: int
    name: str
    unit: str
    quantity: float
    updated_at: datetime


def normalize_inventory_sort(value: Any) -> str:
    """Return a supported inventory sort key, defaulting to newest first."""
    sort = str(value or "").strip()
    return sort if sort in INVENTORY_SORTS else INVENTORY_SORT_UPDATED_DESC


def parse_inventory_quantity(value: Any) -> float | None:
    """Parse a non-negative inventory amount from form input."""
    try:
        quantity = float(value)
    except (TypeError, ValueError):
        return None
    return quantity if quantity >= 0 else None


async def load_inventory(
    owner_id: int, sort: str = INVENTORY_SORT_UPDATED_DESC
) -> list[InventoryRow]:
    """Return a user's inventory items in the requested order.

    Args:
        owner_id: The user whose inventory to load.
        sort: One of :data:`INVENTORY_SORTS`.

    Returns:
        Inventory rows sorted by last update (newest or oldest first) or by
        ingredient name.
    """
    order = ("updated_at", "id")
    if sort == INVENTORY_SORT_UPDATED_DESC:
        order = ("-updated_at", "-id")
    rows = (
        await InventoryItem.filter(owner_id=owner_id)
        .select_related("ingredient", "unit")
        .order_by(*order)
    )
    prepared = [
        InventoryRow(
            id=row.id,
            ingredient_id=row.ingredient.id,
            name=row.ingredient.name,
            unit=row.unit.abbrev,
            quantity=row.quantity,
            updated_at=row.updated_at,
        )
        for row in rows
    ]
    if sort == INVENTORY_SORT_NAME:
        prepared.sort(key=lambda row: (row["name"].lower(), row["unit"].lower()))
    return prepared


async def _resolve_ingredient_and_unit(
    owner_id: int, name: Any, quantity_raw: Any, unit_abbrev: Any
) -> tuple[int, float, int, None] | tuple[None, None, None, str]:
    """Validate inventory input and resolve ingredient/unit ids.

    Returns:
        On success ``(ingredient_id, quantity, unit_id, None)``; on failure
        ``(None, None, None, error_message)``.
    """
    clean_name = str(name or "").strip()
    if not clean_name:
        return None, None, None, t("message.inventory.ingredient_required")

    quantity = parse_inventory_quantity(quantity_raw)
    if quantity is None:
        return None, None, None, t("message.inventory.non_negative_amount")

    clean_unit = str(unit_abbrev or "").strip()
    if not clean_unit:
        return None, None, None, t("message.inventory.unit_required")
    unit = await Unit.find(clean_unit, owner_id=owner_id)
    if unit is None:
        return (
            None,
            None,
            None,
            t("message.inventory.unit_not_found", unit=clean_unit),
        )

    ingredient, _ = await get_or_create_ingredient(owner_id, clean_name)
    return ingredient.id, quantity, unit.id, None


async def add_inventory_item(
    owner_id: int, name: Any, quantity_raw: Any, unit_abbrev: Any
) -> tuple[bool, str]:
    """Add stock for a user, merging into an existing ingredient/unit item.

    Args:
        owner_id: The user adding stock.
        name: Ingredient name; created in the catalog when new.
        quantity_raw: Raw amount from the form (zero or more).
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

    existing = await InventoryItem.get_or_none(
        owner_id=owner_id, ingredient_id=ingredient_id, unit_id=unit_id
    )
    if existing is not None:
        existing.quantity = round(existing.quantity + quantity, 6)
        await existing.save()
        return True, t("message.inventory.merged")

    await InventoryItem.create(
        owner_id=owner_id,
        ingredient_id=ingredient_id,
        unit_id=unit_id,
        quantity=quantity,
    )
    return True, t("message.inventory.added")


async def update_inventory_item(
    owner_id: int,
    item_id: int,
    name: Any,
    quantity_raw: Any,
    unit_abbrev: Any,
) -> tuple[bool, str]:
    """Update an owned inventory item, merging into a duplicate combination.

    When the edited ingredient/unit already exists as another item, the edited
    amount is added to that item and the edited item is removed.

    Returns:
        A success flag and a message describing the outcome.
    """
    row = await InventoryItem.get_or_none(id=item_id, owner_id=owner_id)
    if row is None:
        return False, t("message.inventory.not_found")

    ingredient_id, quantity, unit_id, error = await _resolve_ingredient_and_unit(
        owner_id, name, quantity_raw, unit_abbrev
    )
    if error is not None:
        return False, error
    assert ingredient_id is not None and quantity is not None and unit_id is not None

    duplicate = (
        await InventoryItem.filter(
            owner_id=owner_id, ingredient_id=ingredient_id, unit_id=unit_id
        )
        .exclude(id=item_id)
        .first()
    )
    if duplicate is not None:
        duplicate.quantity = round(duplicate.quantity + quantity, 6)
        await duplicate.save()
        await row.delete()
        return True, t("message.inventory.merged")

    row.ingredient_id = ingredient_id
    row.unit_id = unit_id
    row.quantity = quantity
    await row.save()
    return True, t("message.inventory.updated")


async def delete_inventory_item(owner_id: int, item_id: int) -> bool:
    """Delete an owned inventory item.

    Returns:
        ``True`` when an inventory item was deleted, otherwise ``False``.
    """
    row = await InventoryItem.get_or_none(id=item_id, owner_id=owner_id)
    if row is None:
        return False
    await row.delete()
    return True


async def ensure_inventory_item(
    owner_id: int, ingredient_id: int, unit_abbrev: str
) -> bool:
    """Create an empty (amount 0) inventory item when the combination is missing.

    Used when the user marks a grocery line as already-have, so the item shows
    up in the inventory ready for an amount to be filled in.

    Returns:
        ``True`` when a new inventory item was created.
    """
    unit = await Unit.filter(owner_id=owner_id, abbrev=unit_abbrev.strip()).first()
    if unit is None:
        return False
    _row, created = await InventoryItem.get_or_create(
        owner_id=owner_id,
        ingredient_id=ingredient_id,
        unit_id=unit.id,
        defaults={"quantity": 0},
    )
    return created
