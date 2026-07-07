"""Week menu planning state and helpers."""

from __future__ import annotations

import random
from typing import Any, TypedDict

from litestar import Request

WEEK_DAYS: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

DAY_LABELS: dict[str, str] = {
    "monday": "Monday",
    "tuesday": "Tuesday",
    "wednesday": "Wednesday",
    "thursday": "Thursday",
    "friday": "Friday",
    "saturday": "Saturday",
    "sunday": "Sunday",
}

SESSION_KEY = "week_menu"
START_DAY_SESSION_KEY = "week_menu_start_day"


class DaySlot(TypedDict):
    """A single day in the week menu."""

    recipe_id: int | None
    pinned: bool


def is_valid_day(day: str) -> bool:
    """Return whether ``day`` is a supported weekday key."""
    return day in WEEK_DAYS


def load_start_day(request: Request) -> str:
    """Load preferred start day from session."""
    value = request.session.get(START_DAY_SESSION_KEY, "monday")
    if not isinstance(value, str) or not is_valid_day(value):
        return "monday"
    return value


def save_start_day(request: Request, day: str) -> None:
    """Persist preferred start day to session."""
    if not is_valid_day(day):
        msg = f"Unknown day: {day}"
        raise ValueError(msg)
    request.session[START_DAY_SESSION_KEY] = day


def ordered_week_days(start_day: str) -> list[str]:
    """Return weekdays rotated to begin at ``start_day``."""
    if not is_valid_day(start_day):
        msg = f"Unknown day: {start_day}"
        raise ValueError(msg)
    index = WEEK_DAYS.index(start_day)
    return list(WEEK_DAYS[index:]) + list(WEEK_DAYS[:index])


def empty_week_menu() -> dict[str, DaySlot]:
    """Return a week menu with empty unpinned slots."""
    return {day: DaySlot(recipe_id=None, pinned=False) for day in WEEK_DAYS}


def load_week_menu(request: Request) -> dict[str, DaySlot]:
    """Load week menu state from the session, filling missing days."""
    menu = empty_week_menu()
    stored = request.session.get(SESSION_KEY, {})
    if not isinstance(stored, dict):
        return menu

    for day in WEEK_DAYS:
        day_data = stored.get(day)
        if not isinstance(day_data, dict):
            continue
        recipe_id = day_data.get("recipe_id")
        pinned = bool(day_data.get("pinned", False))
        menu[day] = DaySlot(
            recipe_id=int(recipe_id) if recipe_id is not None else None,
            pinned=pinned,
        )
    return menu


def save_week_menu(request: Request, menu: dict[str, DaySlot]) -> None:
    """Persist week menu state to the session."""
    request.session[SESSION_KEY] = menu


def toggle_pin(menu: dict[str, DaySlot], day: str) -> dict[str, DaySlot]:
    """Toggle whether a day is pinned against rerolls."""
    if not is_valid_day(day):
        msg = f"Unknown day: {day}"
        raise ValueError(msg)
    slot = menu[day]
    slot["pinned"] = not slot["pinned"]
    return menu


def set_day_recipe(
    menu: dict[str, DaySlot], day: str, recipe_id: int | None
) -> dict[str, DaySlot]:
    """Assign a recipe to a day."""
    if not is_valid_day(day):
        msg = f"Unknown day: {day}"
        raise ValueError(msg)
    menu[day]["recipe_id"] = recipe_id
    return menu


def randomize_week_menu(
    menu: dict[str, DaySlot], recipe_ids: list[int]
) -> dict[str, DaySlot]:
    """Fill unpinned days with random enabled recipes, avoiding duplicates when possible."""
    if not recipe_ids:
        return menu

    used_ids = {
        slot["recipe_id"]
        for day, slot in menu.items()
        if slot["pinned"] and slot["recipe_id"] is not None
    }
    unpinned_days = [day for day in WEEK_DAYS if not menu[day]["pinned"]]
    available_ids = [recipe_id for recipe_id in recipe_ids if recipe_id not in used_ids]

    for day in unpinned_days:
        if not available_ids:
            available_ids = list(recipe_ids)
        chosen_id = random.choice(available_ids)
        menu[day]["recipe_id"] = chosen_id
        used_ids.add(chosen_id)
        if len(available_ids) > 1:
            available_ids.remove(chosen_id)
        elif available_ids == [chosen_id] and len(recipe_ids) > 1:
            available_ids = [rid for rid in recipe_ids if rid != chosen_id] or list(
                recipe_ids
            )

    return menu


async def build_day_rows(
    menu: dict[str, DaySlot], recipes_by_id: dict[int, Any], start_day: str = "monday"
) -> list[dict[str, Any]]:
    """Build template rows for each weekday."""
    rows: list[dict[str, Any]] = []
    for day in ordered_week_days(start_day):
        slot = menu[day]
        recipe = recipes_by_id.get(slot["recipe_id"]) if slot["recipe_id"] else None
        rows.append(
            {
                "day": day,
                "label": DAY_LABELS[day],
                "recipe": recipe,
                "pinned": slot["pinned"],
            }
        )
    return rows
