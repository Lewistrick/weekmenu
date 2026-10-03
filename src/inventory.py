"""Per-user kitchen inventory, stored in the database.

Inventory items are amounts of an ingredient (in one unit) a user has at home.
There is at most one item per ingredient/unit combination; adding or editing an
item into an existing combination merges the two by adding their amounts.

How inventory interacts with the grocery list (reserving stock for lines on the
already-have list) lives in :mod:`src.plan_store`.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, TypedDict

from src.catalog import get_or_create_ingredient
from src.categories import CategoryInfo, CategorySection
from src.i18n.service import t
from src.models import Ingredient, InventoryItem, Unit

INVENTORY_SORT_UPDATED_DESC = "updated_desc"
INVENTORY_SORT_UPDATED_ASC = "updated_asc"
INVENTORY_SORT_NAME = "name"
# Alphabetical within each category; the caller adds the category headings.
INVENTORY_SORT_CATEGORY = "category"
# Rows with amount 0 first (0 is 0 in any unit); the caller adds the groups.
INVENTORY_SORT_EMPTY_FIRST = "empty_first"
INVENTORY_SORTS = (
    INVENTORY_SORT_UPDATED_DESC,
    INVENTORY_SORT_UPDATED_ASC,
    INVENTORY_SORT_NAME,
    INVENTORY_SORT_CATEGORY,
    INVENTORY_SORT_EMPTY_FIRST,
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
    if sort in (
        INVENTORY_SORT_NAME,
        INVENTORY_SORT_CATEGORY,
        INVENTORY_SORT_EMPTY_FIRST,
    ):
        prepared.sort(key=lambda row: (row["name"].lower(), row["unit"].lower()))
    return prepared


def group_by_stock(
    items: Sequence[Mapping[str, Any]],
    ingredient_category_ids: Mapping[int, int | None],
    categories: Sequence[CategoryInfo],
    *,
    empty_label: str,
    in_stock_label: str,
) -> list[CategorySection]:
    """Split inventory rows into an "empty" and an "in stock" group.

    A row is empty when its amount is zero. That is judged per row (ingredient
    and unit), so amounts in different units never need comparing. Inside a
    group rows follow the user's shelf order, then name, then unit; rows of
    ingredients without a shelf come last.

    Args:
        items: Inventory rows (``ingredient_id``, ``name``, ``unit``, ``quantity``).
        ingredient_category_ids: Ingredient id to shelf (category) id.
        categories: The user's shelves, in order.
        empty_label: Heading for the empty group.
        in_stock_label: Heading for the in-stock group.

    Returns:
        The non-empty groups, empty rows first.
    """
    shelf_position = {category["id"]: i for i, category in enumerate(categories)}
    unshelved = len(shelf_position)

    def order(item: Mapping[str, Any]) -> tuple[int, str, str]:
        shelf_id = ingredient_category_ids.get(item["ingredient_id"])
        return (
            shelf_position.get(shelf_id, unshelved),
            str(item["name"]).lower(),
            str(item["unit"]).lower(),
        )

    empty = sorted((item for item in items if item["quantity"] <= 0), key=order)
    in_stock = sorted((item for item in items if item["quantity"] > 0), key=order)
    groups = ((empty_label, empty), (in_stock_label, in_stock))
    return [
        CategorySection(category_id=None, name=label, icon="", entries=list(rows))
        for label, rows in groups
        if rows
    ]


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


async def _add_stock(
    owner_id: int, ingredient_id: int, unit_id: int, quantity: float
) -> bool:
    """Add an amount to the item for this ingredient/unit, creating it if needed.

    Returns:
        ``True`` when the amount was added to an existing item (a merge).
    """
    existing = await InventoryItem.get_or_none(
        owner_id=owner_id, ingredient_id=ingredient_id, unit_id=unit_id
    )
    if existing is not None:
        existing.quantity = round(existing.quantity + quantity, 6)
        await existing.save()
        return True
    await InventoryItem.create(
        owner_id=owner_id,
        ingredient_id=ingredient_id,
        unit_id=unit_id,
        quantity=quantity,
    )
    return False


async def add_stock(
    owner_id: int, ingredient_id: int, unit_abbrev: str, quantity: float
) -> bool:
    """Add bought stock to the inventory, summing into an existing item.

    Args:
        owner_id: The user whose inventory to change.
        ingredient_id: One of the user's ingredients.
        unit_abbrev: Abbreviation of one of the user's units.
        quantity: The amount to add (more than zero).

    Returns:
        ``True`` when stock was added, ``False`` when the unit is unknown, the
        ingredient is not the user's, or the amount is not positive.
    """
    if (
        quantity <= 0
        or not await Ingredient.filter(id=ingredient_id, owner_id=owner_id).exists()
    ):
        return False
    unit = await Unit.filter(owner_id=owner_id, abbrev=unit_abbrev.strip()).first()
    if unit is None:
        return False
    await _add_stock(owner_id, ingredient_id, unit.id, quantity)
    return True


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

    merged = await _add_stock(owner_id, ingredient_id, unit_id, quantity)
    return True, t("message.inventory.merged" if merged else "message.inventory.added")


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
