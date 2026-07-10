"""Database persistence for week menus, grocery lists, and user preferences."""

from __future__ import annotations

from src.models import (
    GroceryListItem,
    Unit,
    UserPreference,
    WeekMenuSlot,
    WeekMenuTagConstraint,
)
from src.week_menu import (
    DEFAULT_SERVINGS,
    GroceryItem,
    TagConstraintMode,
    TagGroupConstraint,
    WEEK_DAYS,
    DaySlot,
    _normalize_constraint,
    empty_week_menu,
    grocery_line_key,
    is_valid_day,
    normalize_servings,
)

GROCERY_STATUS_ACTIVE = "active"
GROCERY_STATUS_TO_CHECK = "to_check"
GROCERY_STATUS_ALREADY_HAVE = "already_have"


async def ensure_user_preference(user_id: int) -> UserPreference:
    """Return a user's preference row, creating defaults when missing."""
    preference, _created = await UserPreference.get_or_create(
        user_id=user_id,
        defaults={
            "language": "🇬🇧 English",
            "default_servings": DEFAULT_SERVINGS,
            "start_day": "monday",
            "include_public": False,
            "grocery_list_initialized": False,
        },
    )
    return preference


async def load_start_day(user_id: int) -> str:
    """Load preferred start day from the database."""
    preference = await ensure_user_preference(user_id)
    day = preference.start_day
    if not is_valid_day(day):
        return "monday"
    return day


async def save_start_day(user_id: int, day: str) -> None:
    """Persist preferred start day to the database."""
    if not is_valid_day(day):
        msg = f"Unknown day: {day}"
        raise ValueError(msg)
    preference = await ensure_user_preference(user_id)
    preference.start_day = day
    await preference.save()


async def load_include_public(user_id: int) -> bool:
    """Load whether week-menu actions should include public recipes."""
    preference = await ensure_user_preference(user_id)
    return bool(preference.include_public)


async def save_include_public(user_id: int, include_public: bool) -> None:
    """Persist whether week-menu actions should include public recipes."""
    preference = await ensure_user_preference(user_id)
    preference.include_public = include_public
    await preference.save()


async def load_week_menu(
    user_id: int, default_servings: int = DEFAULT_SERVINGS
) -> dict[str, DaySlot]:
    """Load week menu state from the database, filling missing days."""
    menu = empty_week_menu(default_servings=default_servings)
    rows = await WeekMenuSlot.filter(user_id=user_id).select_related("recipe")
    for row in rows:
        if not is_valid_day(row.day):
            continue
        recipe_id = row.recipe.id if row.recipe is not None else None
        menu[row.day] = DaySlot(
            recipe_id=recipe_id,
            pinned=bool(row.pinned),
            servings=normalize_servings(
                row.servings, default_servings=default_servings
            ),
        )
    return menu


async def save_week_menu(user_id: int, menu: dict[str, DaySlot]) -> None:
    """Persist week menu state to the database."""
    existing = {row.day: row for row in await WeekMenuSlot.filter(user_id=user_id)}
    for day in WEEK_DAYS:
        slot = menu[day]
        row = existing.get(day)
        if row is None:
            await WeekMenuSlot.create(
                user_id=user_id,
                day=day,
                recipe_id=slot["recipe_id"],
                pinned=slot["pinned"],
                servings=slot["servings"],
            )
            continue
        row.recipe_id = slot["recipe_id"]
        row.pinned = slot["pinned"]
        row.servings = slot["servings"]
        await row.save()


async def load_tag_constraints(
    user_id: int, category_ids: list[int]
) -> list[TagGroupConstraint]:
    """Load tag constraints from the database, filling defaults for each group."""
    rows = await WeekMenuTagConstraint.filter(user_id=user_id).select_related(
        "category", "tag"
    )
    by_category = {row.category.id: row for row in rows}
    constraints: list[TagGroupConstraint] = []
    for category_id in category_ids:
        row = by_category.get(category_id)
        if row is None:
            constraints.append(
                TagGroupConstraint(
                    category_id=category_id,
                    mode=TagConstraintMode.OFF,
                    tag_id=None,
                    minimum_count=1,
                )
            )
            continue
        constraints.append(
            _normalize_constraint(
                {
                    "mode": row.mode,
                    "tag_id": row.tag.id if row.tag is not None else None,
                    "minimum_count": row.minimum_count,
                },
                category_id,
            )
        )
    return constraints


async def save_tag_constraints(
    user_id: int, constraints: list[TagGroupConstraint]
) -> None:
    """Persist tag constraints to the database."""
    existing = {
        row.category.id: row
        for row in await WeekMenuTagConstraint.filter(user_id=user_id)
    }
    seen_category_ids: set[int] = set()
    for constraint in constraints:
        category_id = constraint["category_id"]
        seen_category_ids.add(category_id)
        row = existing.get(category_id)
        if row is None:
            await WeekMenuTagConstraint.create(
                user_id=user_id,
                category_id=category_id,
                mode=constraint["mode"],
                tag_id=constraint["tag_id"],
                minimum_count=constraint["minimum_count"],
            )
            continue
        row.mode = constraint["mode"]
        row.tag_id = constraint["tag_id"]
        row.minimum_count = constraint["minimum_count"]
        await row.save()

    for category_id, row in existing.items():
        if category_id not in seen_category_ids:
            await row.delete()


async def _unit_id_by_abbrev(owner_id: int, abbrev: str) -> int | None:
    """Resolve a unit abbreviation to its database id for one user."""
    unit = await Unit.filter(owner_id=owner_id, abbrev=abbrev.strip()).first()
    return unit.id if unit is not None else None


async def _grocery_rows_to_items(rows: list[GroceryListItem]) -> list[GroceryItem]:
    """Convert grocery list rows into template-friendly items."""
    items: list[GroceryItem] = []
    for row in rows:
        items.append(
            GroceryItem(
                ingredient_id=row.ingredient.id,
                name=row.ingredient.name if row.ingredient else "",
                unit=row.unit.abbrev if row.unit else "",
                quantity=float(row.quantity),
            )
        )
    return items


async def load_grocery_list(user_id: int) -> list[GroceryItem]:
    """Load the persisted grocery list for one user."""
    rows = await GroceryListItem.filter(user_id=user_id).select_related(
        "ingredient", "unit"
    )
    return await _grocery_rows_to_items(list(rows))


async def is_grocery_list_initialized(user_id: int) -> bool:
    """Return whether a grocery list has been generated for this user."""
    preference = await ensure_user_preference(user_id)
    return bool(preference.grocery_list_initialized)


async def is_grocery_list_empty(user_id: int) -> bool:
    """Return whether the user has no persisted grocery list lines."""
    return not await GroceryListItem.filter(user_id=user_id).exists()


async def _get_grocery_row(
    user_id: int, ingredient_id: int, unit_abbrev: str
) -> GroceryListItem | None:
    """Return one grocery list row by ingredient and unit abbrev."""
    unit_id = await _unit_id_by_abbrev(user_id, unit_abbrev)
    if unit_id is None:
        return None
    return (
        await GroceryListItem.filter(
            user_id=user_id,
            ingredient_id=ingredient_id,
            unit_id=unit_id,
        )
        .select_related("ingredient", "unit")
        .first()
    )


async def save_grocery_list(user_id: int, items: list[GroceryItem]) -> None:
    """Persist the grocery list for one user, preserving sorting state."""
    existing_rows = list(
        await GroceryListItem.filter(user_id=user_id).select_related(
            "ingredient", "unit"
        )
    )
    existing_by_key = {
        (row.ingredient.id, row.unit.abbrev if row.unit else ""): row
        for row in existing_rows
    }
    seen_keys: set[tuple[int, str]] = set()
    for item in items:
        unit_abbrev = item["unit"].strip()
        unit_id = await _unit_id_by_abbrev(user_id, unit_abbrev)
        if unit_id is None:
            continue
        key = (item["ingredient_id"], unit_abbrev)
        seen_keys.add(key)
        row = existing_by_key.get(key)
        if row is None:
            await GroceryListItem.create(
                user_id=user_id,
                ingredient_id=item["ingredient_id"],
                unit_id=unit_id,
                quantity=item["quantity"],
            )
            continue
        row.quantity = item["quantity"]
        await row.save()

    for key, row in existing_by_key.items():
        if key not in seen_keys:
            await row.delete()

    preference = await ensure_user_preference(user_id)
    preference.grocery_list_initialized = True
    await preference.save()


async def clear_grocery_list(user_id: int) -> None:
    """Remove the persisted grocery list for one user."""
    await GroceryListItem.filter(user_id=user_id).delete()
    preference = await ensure_user_preference(user_id)
    preference.grocery_list_initialized = False
    await preference.save()


async def load_already_have_line_keys(user_id: int) -> set[str]:
    """Load grocery line keys the user already has for this grocery list."""
    rows = await GroceryListItem.filter(
        user_id=user_id, status=GROCERY_STATUS_ALREADY_HAVE
    ).select_related("unit", "ingredient")
    return {
        grocery_line_key(row.ingredient.id, row.unit.abbrev if row.unit else "")
        for row in rows
    }


async def load_to_check_line_keys(user_id: int) -> set[str]:
    """Load grocery line keys the user wants to verify before buying."""
    rows = await GroceryListItem.filter(
        user_id=user_id, status=GROCERY_STATUS_TO_CHECK
    ).select_related("unit", "ingredient")
    return {
        grocery_line_key(row.ingredient.id, row.unit.abbrev if row.unit else "")
        for row in rows
    }


async def load_grocery_line_shops(user_id: int) -> dict[str, int]:
    """Load per-line shop overrides for the current grocery list."""
    rows = await GroceryListItem.filter(
        user_id=user_id, shop_id__isnull=False
    ).select_related("unit", "shop", "ingredient")
    line_shops: dict[str, int] = {}
    for row in rows:
        if row.shop is None:
            continue
        line_shops[
            grocery_line_key(row.ingredient.id, row.unit.abbrev if row.unit else "")
        ] = row.shop.id
    return line_shops


async def _set_grocery_status(
    user_id: int, ingredient_id: int, unit: str, status: str
) -> None:
    """Update the sorting status for one grocery line."""
    row = await _get_grocery_row(user_id, ingredient_id, unit)
    if row is None:
        return
    row.status = status
    await row.save()


async def mark_already_have_line(user_id: int, ingredient_id: int, unit: str) -> None:
    """Mark one grocery line as already available at home."""
    await _set_grocery_status(user_id, ingredient_id, unit, GROCERY_STATUS_ALREADY_HAVE)


async def unmark_already_have_line(user_id: int, ingredient_id: int, unit: str) -> None:
    """Remove one grocery line from the already-have list."""
    row = await _get_grocery_row(user_id, ingredient_id, unit)
    if row is None or row.status != GROCERY_STATUS_ALREADY_HAVE:
        return
    row.status = GROCERY_STATUS_ACTIVE
    await row.save()


async def mark_to_check_line(user_id: int, ingredient_id: int, unit: str) -> None:
    """Move one grocery line to the to-check list."""
    await _set_grocery_status(user_id, ingredient_id, unit, GROCERY_STATUS_TO_CHECK)


async def unmark_to_check_line(user_id: int, ingredient_id: int, unit: str) -> None:
    """Return one grocery line from the to-check list to active sorting."""
    row = await _get_grocery_row(user_id, ingredient_id, unit)
    if row is None or row.status != GROCERY_STATUS_TO_CHECK:
        return
    row.status = GROCERY_STATUS_ACTIVE
    await row.save()


async def clear_to_check(user_id: int) -> None:
    """Return every to-check grocery line to active sorting."""
    await GroceryListItem.filter(
        user_id=user_id, status=GROCERY_STATUS_TO_CHECK
    ).update(status=GROCERY_STATUS_ACTIVE)


async def clear_already_have(user_id: int) -> None:
    """Return every already-have grocery line to active sorting."""
    await GroceryListItem.filter(
        user_id=user_id, status=GROCERY_STATUS_ALREADY_HAVE
    ).update(status=GROCERY_STATUS_ACTIVE)


async def set_grocery_line_shop(
    user_id: int, ingredient_id: int, unit: str, shop_id: int
) -> None:
    """Assign one grocery line to a shop for the current list."""
    row = await _get_grocery_row(user_id, ingredient_id, unit)
    if row is None:
        return
    row.shop_id = shop_id
    row.status = GROCERY_STATUS_ACTIVE
    await row.save()


async def clear_grocery_line_shops(user_id: int) -> None:
    """Remove per-line shop overrides for the current grocery list."""
    await GroceryListItem.filter(user_id=user_id).update(shop_id=None)


async def reset_grocery_plan(user_id: int) -> None:
    """Clear grocery-list sorting state for a freshly generated list."""
    await GroceryListItem.filter(user_id=user_id).update(
        status=GROCERY_STATUS_ACTIVE,
        shop_id=None,
    )


async def remove_grocery_line_state(user_id: int, line_keys: set[str]) -> None:
    """Drop sorting state for grocery lines that no longer exist."""
    if not line_keys:
        return
    rows = await GroceryListItem.filter(user_id=user_id).select_related(
        "unit", "ingredient"
    )
    for row in rows:
        key = grocery_line_key(row.ingredient.id, row.unit.abbrev if row.unit else "")
        if key in line_keys:
            row.status = GROCERY_STATUS_ACTIVE
            row.shop_id = None
            await row.save()


async def find_grocery_line_in_store(
    user_id: int, ingredient_id: int, unit: str
) -> GroceryItem | None:
    """Return a grocery line from the database list, if present."""
    row = await _get_grocery_row(user_id, ingredient_id, unit)
    if row is None:
        return None
    items = await _grocery_rows_to_items([row])
    return items[0] if items else None


async def empty_to_check_list(user_id: int) -> None:
    """Remove to-check groceries from the plan entirely."""
    await GroceryListItem.filter(
        user_id=user_id, status=GROCERY_STATUS_TO_CHECK
    ).delete()


async def empty_already_have_list(user_id: int) -> None:
    """Remove already-have groceries from the plan entirely."""
    await GroceryListItem.filter(
        user_id=user_id, status=GROCERY_STATUS_ALREADY_HAVE
    ).delete()


async def mark_shop_already_have(
    user_id: int,
    shop_id: int,
    items: list[GroceryItem],
    ingredient_shop_ids: dict[int, int | None],
    line_shop_ids: dict[str, int],
) -> None:
    """Mark every grocery line in one shop section as already available."""
    from src.week_menu import resolve_grocery_line_shop_id

    for item in items:
        if (
            resolve_grocery_line_shop_id(item, ingredient_shop_ids, line_shop_ids)
            == shop_id
        ):
            await mark_already_have_line(user_id, item["ingredient_id"], item["unit"])


async def prune_orphaned_grocery_lines(
    user_id: int, items: list[GroceryItem] | None = None
) -> list[GroceryItem]:
    """Remove grocery lines whose ingredients no longer exist for the user."""
    working = list(items if items is not None else await load_grocery_list(user_id))
    if not working:
        return working

    from src.models import Ingredient

    ingredient_ids = {item["ingredient_id"] for item in working}
    valid_ids = set(
        await Ingredient.filter(id__in=ingredient_ids, owner_id=user_id).values_list(
            "id", flat=True
        )
    )
    pruned = [item for item in working if item["ingredient_id"] in valid_ids]
    if len(pruned) == len(working):
        return pruned

    invalid_ids = ingredient_ids - valid_ids
    await GroceryListItem.filter(
        user_id=user_id, ingredient_id__in=invalid_ids
    ).delete()
    if len(pruned) != len(working):
        preference = await ensure_user_preference(user_id)
        if not pruned:
            preference.grocery_list_initialized = False
        await preference.save()
    return pruned


async def update_grocery_line(
    user_id: int,
    ingredient_id: int,
    old_unit: str,
    *,
    quantity: float,
    unit: str,
    items: list[GroceryItem] | None = None,
) -> tuple[bool, str | None]:
    """Update one grocery line, merging when the target unit already exists."""
    from src.week_menu import find_grocery_line

    normalized_unit = unit.strip()
    old_unit_normalized = old_unit.strip()
    if not normalized_unit:
        return False, None

    working_items = list(
        items if items is not None else await load_grocery_list(user_id)
    )
    current = find_grocery_line(working_items, ingredient_id, old_unit_normalized)
    if current is None:
        return False, None

    merge_message: str | None = None
    if normalized_unit == old_unit_normalized:
        current["quantity"] = round(quantity, 2)
        await save_grocery_list(user_id, working_items)
        return True, None

    duplicate = find_grocery_line(working_items, ingredient_id, normalized_unit)
    remaining = [
        item
        for item in working_items
        if not (
            item["ingredient_id"] == ingredient_id
            and item["unit"] == old_unit_normalized
        )
    ]
    if duplicate is not None:
        for item in remaining:
            if (
                item["ingredient_id"] == ingredient_id
                and item["unit"] == normalized_unit
            ):
                item["quantity"] = round(item["quantity"] + quantity, 2)
                label = item["name"].strip() or f"ingredient {ingredient_id}"
                merge_message = f"Combined with existing {label} ({normalized_unit})."
                break
    else:
        remaining.append(
            GroceryItem(
                ingredient_id=ingredient_id,
                name=current["name"],
                unit=normalized_unit,
                quantity=round(quantity, 2),
            )
        )

    await save_grocery_list(user_id, remaining)
    return True, merge_message


async def add_items_to_grocery_list(
    user_id: int, new_items: list[GroceryItem]
) -> list[GroceryItem]:
    """Add items to the current grocery list, merging matching lines."""
    from src.week_menu import hydrate_grocery_item_names, merge_grocery_items

    existing: list[GroceryItem] = []
    if await is_grocery_list_initialized(user_id):
        existing = await hydrate_grocery_item_names(
            user_id, await load_grocery_list(user_id)
        )
    merged = merge_grocery_items(existing, new_items)
    await save_grocery_list(user_id, merged)
    return merged


async def has_grocery_list_items(user_id: int) -> bool:
    """Return whether the user has a non-empty persisted grocery list."""
    return await is_grocery_list_initialized(
        user_id
    ) and not await is_grocery_list_empty(user_id)


async def migrate_json_user_settings(
    user_id: int,
    *,
    language: str,
    servings: int,
) -> None:
    """Import legacy JSON settings into the database once."""
    preference = await ensure_user_preference(user_id)
    preference.language = language
    preference.default_servings = servings
    await preference.save()
