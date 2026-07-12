"""Per-user unit catalog helpers."""

from __future__ import annotations

from typing import TypedDict

from src.i18n.service import t
from src.models import GroceryListItem, RecipeIngredient, Unit, WeeklyGrocery


class UnitRow(TypedDict):
    """One unit prepared for display on the management page."""

    id: int
    abbrev: str
    single: str
    plural: str
    incomplete: bool


def _normalize_text(value: object) -> str:
    """Return trimmed text from form input."""
    return str(value or "").strip()


def unit_is_complete(abbrev: str, single: str, plural: str) -> bool:
    """Return whether a unit has abbreviation, singular, and plural labels."""
    return bool(abbrev.strip() and single.strip() and plural.strip())


async def load_units(owner_id: int) -> list[UnitRow]:
    """Return a user's units sorted by abbreviation."""
    rows = await Unit.filter(owner_id=owner_id).order_by("abbrev")
    return [
        UnitRow(
            id=row.id,
            abbrev=row.abbrev,
            single=row.single or "",
            plural=row.plural or "",
            incomplete=not unit_is_complete(
                row.abbrev, row.single or "", row.plural or ""
            ),
        )
        for row in rows
    ]


async def unit_is_in_use(unit_id: int) -> bool:
    """Return whether a unit is referenced by recipes, groceries, or lists."""
    if await RecipeIngredient.filter(unit_id=unit_id).exists():
        return True
    if await WeeklyGrocery.filter(unit_id=unit_id).exists():
        return True
    return await GroceryListItem.filter(unit_id=unit_id).exists()


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
    unit.abbrev = abbrev
    unit.single = single
    unit.plural = plural
    await unit.save()
    return True, t("message.units.updated")


async def delete_unit(owner_id: int, unit_id: int) -> tuple[bool, str]:
    """Delete one owned unit when it is not in use.

    Returns:
        A success flag and user-facing message.
    """
    unit = await Unit.get_or_none(id=unit_id, owner_id=owner_id)
    if unit is None:
        return False, t("message.units.not_found")
    if await unit_is_in_use(unit.id):
        return (
            False,
            t("message.units.in_use", abbrev=unit.abbrev),
        )
    await unit.delete()
    return True, t("message.units.deleted")
