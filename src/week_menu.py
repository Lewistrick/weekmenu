"""Week menu planning state and helpers."""

from __future__ import annotations

import random
from enum import StrEnum
from collections.abc import Callable
from typing import Any, TypedDict

from litestar import Request
from loguru import logger

from src.auth import SESSION_USER_KEY
from src.i18n.service import t

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

GROCERY_ACTION_FLASH_KEY = "grocery_action_flash"
GROCERY_SUPPRESS_PRESERVE_KEY = "grocery_suppress_preserve"

DEFAULT_SERVINGS = 2


def _scoped_key(request: Request, base: str) -> str:
    """Return a session key namespaced to the logged-in user.

    Namespacing flash-message keys with the current user id keeps one user's
    notices from leaking to the next account that logs in on the same browser.

    Args:
        request: The incoming request carrying the session.
        base: The base session key.

    Returns:
        The base key suffixed with the current user id, or the base key itself
        when no user is logged in.
    """
    user_id = request.session.get(SESSION_USER_KEY)
    return f"{base}:{user_id}" if user_id is not None else base


class TagConstraintMode(StrEnum):
    """How a tag group constrains week menu randomization."""

    OFF = "off"
    UNIFORM = "uniform"
    VARY = "vary"
    MINIMUM = "minimum"


class TagGroupConstraint(TypedDict):
    """User-selected constraint for one tag group."""

    category_id: int
    mode: str
    tag_id: int | None
    minimum_count: int


RecipeTagsByCategory = dict[int, set[int]]
RecipeTagMap = dict[int, RecipeTagsByCategory]


class DaySlot(TypedDict):
    """A single day in the week menu."""

    recipe_id: int | None
    pinned: bool
    servings: int


class GroceryItem(TypedDict):
    """A single aggregated line on the grocery list."""

    ingredient_id: int
    name: str
    unit: str
    quantity: float


def normalize_servings(value: Any, default_servings: int = DEFAULT_SERVINGS) -> int:
    """Coerce a servings value into a positive integer.

    Args:
        value: Raw servings value from form input.

    Returns:
        A positive integer, falling back to ``default_servings`` when invalid.
    """
    try:
        servings = int(value)
    except (TypeError, ValueError):
        return default_servings
    return servings if servings >= 1 else default_servings


def is_valid_day(day: str) -> bool:
    """Return whether ``day`` is a supported weekday key."""
    return day in WEEK_DAYS


def ordered_week_days(start_day: str) -> list[str]:
    """Return weekdays rotated to begin at ``start_day``."""
    if not is_valid_day(start_day):
        msg = f"Unknown day: {start_day}"
        raise ValueError(msg)
    index = WEEK_DAYS.index(start_day)
    return list(WEEK_DAYS[index:]) + list(WEEK_DAYS[:index])


def empty_week_menu(default_servings: int = DEFAULT_SERVINGS) -> dict[str, DaySlot]:
    """Return a week menu with empty unpinned slots."""
    return {
        day: DaySlot(recipe_id=None, pinned=False, servings=default_servings)
        for day in WEEK_DAYS
    }


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


def set_day_servings(
    menu: dict[str, DaySlot],
    day: str,
    servings: int,
    default_servings: int = DEFAULT_SERVINGS,
) -> dict[str, DaySlot]:
    """Set the number of servings planned for a day."""
    if not is_valid_day(day):
        msg = f"Unknown day: {day}"
        raise ValueError(msg)
    menu[day]["servings"] = normalize_servings(
        servings, default_servings=default_servings
    )
    return menu


def move_day(
    menu: dict[str, DaySlot], day: str, direction: str, start_day: str = "monday"
) -> dict[str, DaySlot]:
    """Swap a day's slot with its neighbour in display order.

    Moving a day exchanges its full slot (recipe, servings, and pin) with the
    adjacent day, so the whole meal moves up or down the week.

    Args:
        menu: Current week menu state.
        day: Day whose slot should move.
        direction: Either ``"up"`` or ``"down"`` relative to display order.
        start_day: Day the week is displayed from, used to resolve neighbours.

    Returns:
        The updated menu. Moving past the first or last day is a no-op.

    Raises:
        ValueError: If ``day`` is unknown or ``direction`` is not up/down.
    """
    if not is_valid_day(day):
        msg = f"Unknown day: {day}"
        raise ValueError(msg)
    if direction not in {"up", "down"}:
        msg = f"Unknown direction: {direction}"
        raise ValueError(msg)

    order = ordered_week_days(start_day)
    index = order.index(day)
    target_index = index - 1 if direction == "up" else index + 1
    if target_index < 0 or target_index >= len(order):
        return menu

    target_day = order[target_index]
    menu[day], menu[target_day] = menu[target_day], menu[day]
    return menu


def assign_recipe_to_unpinned_day(
    menu: dict[str, DaySlot], recipe_id: int, start_day: str = "monday"
) -> str | None:
    """Assign recipe to first unpinned day in display order.

    Returns:
        Assigned day key, or ``None`` when all days are pinned.
    """
    for day in ordered_week_days(start_day):
        if not menu[day]["pinned"]:
            menu[day]["recipe_id"] = recipe_id
            return day
    return None


def default_tag_constraints(category_ids: list[int]) -> list[TagGroupConstraint]:
    """Return disabled constraints for each tag group."""
    return [
        TagGroupConstraint(
            category_id=category_id,
            mode=TagConstraintMode.OFF,
            tag_id=None,
            minimum_count=1,
        )
        for category_id in category_ids
    ]


def _normalize_constraint(raw: dict[str, Any], category_id: int) -> TagGroupConstraint:
    """Coerce stored constraint data into a valid shape."""
    mode_value = str(raw.get("mode", TagConstraintMode.OFF))
    if mode_value not in {item.value for item in TagConstraintMode}:
        mode_value = TagConstraintMode.OFF

    tag_id = raw.get("tag_id")
    minimum_count = raw.get("minimum_count", 1)
    try:
        minimum_count = max(1, min(len(WEEK_DAYS), int(minimum_count)))
    except (TypeError, ValueError):
        minimum_count = 1

    return TagGroupConstraint(
        category_id=category_id,
        mode=mode_value,
        tag_id=int(tag_id) if tag_id is not None else None,
        minimum_count=minimum_count,
    )


def parse_tag_constraints_from_form(
    form_data: dict[str, Any], category_ids: list[int]
) -> list[TagGroupConstraint]:
    """Parse tag constraint settings submitted from the week menu form."""
    constraints: list[TagGroupConstraint] = []
    for category_id in category_ids:
        mode = str(
            form_data.get(f"constraint_mode_{category_id}", TagConstraintMode.OFF)
        )
        if mode not in {item.value for item in TagConstraintMode}:
            mode = TagConstraintMode.OFF

        tag_value = form_data.get(f"constraint_tag_{category_id}")
        tag_id = int(str(tag_value)) if tag_value not in {None, ""} else None

        minimum_raw = form_data.get(f"constraint_min_{category_id}", 1)
        try:
            minimum_count = max(1, min(len(WEEK_DAYS), int(minimum_raw)))
        except (TypeError, ValueError):
            minimum_count = 1

        constraints.append(
            TagGroupConstraint(
                category_id=category_id,
                mode=mode,
                tag_id=tag_id,
                minimum_count=minimum_count,
            )
        )
    return constraints


def resolve_grocery_line_shop_id(
    item: GroceryItem,
    ingredient_shop_ids: dict[int, int | None],
    line_shop_ids: dict[str, int],
) -> int | None:
    """Return the shop id used to group one grocery line."""
    line_key = grocery_line_key(item["ingredient_id"], item["unit"])
    if line_key in line_shop_ids:
        return line_shop_ids[line_key]
    return ingredient_shop_ids.get(item["ingredient_id"])


async def hydrate_grocery_item_names(
    owner_id: int, items: list[GroceryItem]
) -> list[GroceryItem]:
    """Fill missing grocery line names from the ingredient catalog."""
    if not items:
        return items
    missing_ids = {item["ingredient_id"] for item in items if not item["name"].strip()}
    if not missing_ids:
        return items

    from src.models import Ingredient

    names = {
        row["id"]: row["name"]
        for row in await Ingredient.filter(
            id__in=missing_ids, owner_id=owner_id
        ).values("id", "name")
    }
    hydrated: list[GroceryItem] = []
    for item in items:
        name = item["name"].strip() or names.get(
            item["ingredient_id"], f"#{item['ingredient_id']}"
        )
        hydrated.append(
            GroceryItem(
                ingredient_id=item["ingredient_id"],
                name=name,
                unit=item["unit"],
                quantity=item["quantity"],
            )
        )
    return hydrated


def grocery_line_key(ingredient_id: int, unit: str) -> str:
    """Return a stable DOM key for one ingredient-unit grocery line."""
    return f"{ingredient_id}-{unit.strip()}"


def find_grocery_line(
    items: list[GroceryItem], ingredient_id: int, unit: str
) -> GroceryItem | None:
    """Return the grocery line matching an ingredient id and unit."""
    normalized_unit = unit.strip()
    for item in items:
        if item["ingredient_id"] == ingredient_id and item["unit"] == normalized_unit:
            return item
    return None


def ingredient_in_grocery_list(items: list[GroceryItem], ingredient_id: int) -> bool:
    """Return whether an ingredient appears on the grocery list."""
    return any(item["ingredient_id"] == ingredient_id for item in items)


def set_grocery_action_flash(request: Request, message: str) -> None:
    """Store a one-time grocery list action message for the next page load."""
    request.session[_scoped_key(request, GROCERY_ACTION_FLASH_KEY)] = message


def pop_grocery_action_flash(request: Request) -> str | None:
    """Return and clear a one-time grocery list action message."""
    key = _scoped_key(request, GROCERY_ACTION_FLASH_KEY)
    message = request.session.pop(key, None)
    return str(message) if message else None


def set_grocery_suppress_preserve(request: Request) -> None:
    """Skip the preserved-list notice on the next grocery list page load."""
    request.session[_scoped_key(request, GROCERY_SUPPRESS_PRESERVE_KEY)] = True


def pop_grocery_suppress_preserve(request: Request) -> bool:
    """Return and clear the preserved-list notice suppression flag."""
    key = _scoped_key(request, GROCERY_SUPPRESS_PRESERVE_KEY)
    return bool(request.session.pop(key, False))


def parse_grocery_quantity(value: Any) -> float | None:
    """Parse a positive grocery quantity from form input."""
    try:
        quantity = float(value)
    except (TypeError, ValueError):
        return None
    return quantity if quantity > 0 else None


def active_tag_constraints(
    constraints: list[TagGroupConstraint],
) -> list[TagGroupConstraint]:
    """Return only constraints that affect randomization."""
    return [
        constraint
        for constraint in constraints
        if constraint["mode"] != TagConstraintMode.OFF
    ]


def _recipe_tags(
    recipe_id: int,
    recipe_tag_map: RecipeTagMap,
    category_id: int,
) -> set[int]:
    """Return tag ids a recipe has within one category."""
    return set(recipe_tag_map.get(recipe_id, {}).get(category_id, set()))


def _recipe_has_tag(
    recipe_id: int,
    recipe_tag_map: RecipeTagMap,
    category_id: int,
    tag_id: int,
) -> bool:
    """Return whether a recipe carries a specific tag in a category."""
    return tag_id in _recipe_tags(recipe_id, recipe_tag_map, category_id)


def _count_recipes_with_tag(
    assignment: dict[str, int | None],
    recipe_tag_map: RecipeTagMap,
    category_id: int,
    tag_id: int,
) -> int:
    """Count assigned days whose recipe has the given tag."""
    return sum(
        1
        for recipe_id in assignment.values()
        if recipe_id is not None
        and _recipe_has_tag(recipe_id, recipe_tag_map, category_id, tag_id)
    )


def _uniform_allows(
    recipe_id: int,
    constraint: TagGroupConstraint,
    recipe_tag_map: RecipeTagMap,
) -> bool:
    """Return whether a recipe satisfies a same-tag-everywhere constraint."""
    tag_id = constraint["tag_id"]
    if tag_id is None:
        return False
    return _recipe_has_tag(recipe_id, recipe_tag_map, constraint["category_id"], tag_id)


def _vary_allows(
    recipe_id: int,
    assignment: dict[str, int | None],
    constraint: TagGroupConstraint,
    recipe_tag_map: RecipeTagMap,
    *,
    day: str,
) -> bool:
    """Return whether assigning a recipe avoids adjacent tag repeats."""
    category_id = constraint["category_id"]
    candidate_tags = _recipe_tags(recipe_id, recipe_tag_map, category_id)
    if not candidate_tags:
        return True

    day_index = WEEK_DAYS.index(day)
    adjacent_days: tuple[str, ...] = (
        WEEK_DAYS[(day_index - 1) % len(WEEK_DAYS)],
        WEEK_DAYS[(day_index + 1) % len(WEEK_DAYS)],
    )

    for other_day in adjacent_days:
        assigned_id = assignment.get(other_day)
        if assigned_id is None:
            continue
        assigned_tags = _recipe_tags(assigned_id, recipe_tag_map, category_id)
        if candidate_tags & assigned_tags:
            return False

    return True


def _minimum_can_still_be_met(
    assignment: dict[str, int | None],
    remaining_day_count: int,
    constraint: TagGroupConstraint,
    recipe_tag_map: RecipeTagMap,
) -> bool:
    """Return whether a minimum-count constraint can still be satisfied."""
    tag_id = constraint["tag_id"]
    if tag_id is None:
        return False

    current = _count_recipes_with_tag(
        assignment, recipe_tag_map, constraint["category_id"], tag_id
    )
    return current + remaining_day_count >= constraint["minimum_count"]


def _minimum_is_met(
    assignment: dict[str, int | None],
    constraint: TagGroupConstraint,
    recipe_tag_map: RecipeTagMap,
) -> bool:
    """Return whether a minimum-count constraint is satisfied."""
    tag_id = constraint["tag_id"]
    if tag_id is None:
        return False
    return (
        _count_recipes_with_tag(
            assignment, recipe_tag_map, constraint["category_id"], tag_id
        )
        >= constraint["minimum_count"]
    )


def _candidate_is_valid(
    recipe_id: int,
    day: str,
    assignment: dict[str, int | None],
    constraints: list[TagGroupConstraint],
    recipe_tag_map: RecipeTagMap,
    *,
    slots_remaining_after_assign: int,
) -> bool:
    """Return whether a recipe can be assigned under active constraints."""
    hypothetical = dict(assignment)
    hypothetical[day] = recipe_id

    for constraint in constraints:
        mode = constraint["mode"]
        if mode == TagConstraintMode.UNIFORM and not _uniform_allows(
            recipe_id, constraint, recipe_tag_map
        ):
            return False
        if mode == TagConstraintMode.VARY and not _vary_allows(
            recipe_id, assignment, constraint, recipe_tag_map, day=day
        ):
            return False
        if mode == TagConstraintMode.MINIMUM:
            tag_id = constraint["tag_id"]
            if tag_id is None:
                return False
            current = _count_recipes_with_tag(
                hypothetical, recipe_tag_map, constraint["category_id"], tag_id
            )
            if current + slots_remaining_after_assign < constraint["minimum_count"]:
                return False
    return True


def _all_minimums_met(
    assignment: dict[str, int | None],
    constraints: list[TagGroupConstraint],
    recipe_tag_map: RecipeTagMap,
) -> bool:
    """Return whether every minimum-count constraint is satisfied."""
    for constraint in constraints:
        if constraint["mode"] != TagConstraintMode.MINIMUM:
            continue
        if not _minimum_is_met(assignment, constraint, recipe_tag_map):
            return False
    return True


def _ordered_candidates(
    recipe_ids: list[int],
    assignment: dict[str, int | None],
    *,
    rng: random.Random,
) -> list[int]:
    """Return recipe ids to try, preferring recipes used fewer times."""
    usage_count = {
        recipe_id: sum(1 for value in assignment.values() if value == recipe_id)
        for recipe_id in recipe_ids
    }
    candidates = list(recipe_ids)
    rng.shuffle(candidates)
    return sorted(candidates, key=lambda recipe_id: usage_count[recipe_id])


def _solve_random_assignment(
    menu: dict[str, DaySlot],
    recipe_ids: list[int],
    constraints: list[TagGroupConstraint],
    recipe_tag_map: RecipeTagMap,
    *,
    rng: random.Random,
) -> dict[str, int | None] | None:
    """Find a random valid assignment for unpinned days using backtracking."""
    assignment: dict[str, int | None] = {
        day: slot["recipe_id"] for day, slot in menu.items()
    }
    unpinned_days = [day for day in WEEK_DAYS if not menu[day]["pinned"]]

    def backtrack(index: int) -> bool:
        """Try recipe candidates for unpinned days from ``index`` onward."""
        if index == len(unpinned_days):
            return _all_minimums_met(assignment, constraints, recipe_tag_map)

        day = unpinned_days[index]
        slots_after = len(unpinned_days) - index - 1
        previous_recipe_id = assignment[day]
        for recipe_id in _ordered_candidates(recipe_ids, assignment, rng=rng):
            if not _candidate_is_valid(
                recipe_id,
                day,
                assignment,
                constraints,
                recipe_tag_map,
                slots_remaining_after_assign=slots_after,
            ):
                continue

            assignment[day] = recipe_id
            if backtrack(index + 1):
                return True
            assignment[day] = previous_recipe_id

        return False

    if backtrack(0):
        return assignment
    return None


def randomize_week_menu(
    menu: dict[str, DaySlot],
    recipe_ids: list[int],
    *,
    constraints: list[TagGroupConstraint] | None = None,
    recipe_tag_map: RecipeTagMap | None = None,
    rng: random.Random | None = None,
) -> tuple[dict[str, DaySlot], list[str]]:
    """Fill unpinned days with random recipes that satisfy tag constraints.

    Returns:
        Updated menu and any warnings when constraints could not be satisfied.
    """
    warnings: list[str] = []
    if not recipe_ids:
        return menu, warnings

    active_constraints = active_tag_constraints(constraints or [])
    tag_map = recipe_tag_map or {}
    randomizer = rng or random.Random()

    if not active_constraints:
        return _randomize_without_constraints(
            menu, recipe_ids, rng=randomizer
        ), warnings

    for constraint in active_constraints:
        if (
            constraint["mode"]
            in {
                TagConstraintMode.UNIFORM,
                TagConstraintMode.MINIMUM,
            }
            and constraint["tag_id"] is None
        ):
            warnings.append(t("message.week_menu.constraint_select_tag"))
            return menu, warnings

    for _attempt in range(30):
        logger.debug(f"Attempt {_attempt + 1} of randomizing")
        solution = _solve_random_assignment(
            menu,
            recipe_ids,
            active_constraints,
            tag_map,
            rng=randomizer,
        )
        if solution is not None:
            for day in WEEK_DAYS:
                if not menu[day]["pinned"]:
                    menu[day]["recipe_id"] = solution[day]
            return menu, warnings

    warnings.append(t("message.week_menu.constraint_unsatisfied"))
    return menu, warnings


def _randomize_without_constraints(
    menu: dict[str, DaySlot],
    recipe_ids: list[int],
    *,
    rng: random.Random,
) -> dict[str, DaySlot]:
    """Fill unpinned days with random enabled recipes, avoiding duplicates when possible."""
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
        chosen_id = rng.choice(available_ids)
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
    menu: dict[str, DaySlot],
    recipes_by_id: dict[int, Any],
    start_day: str = "monday",
    day_label_fn: Callable[[str], str] | None = None,
) -> list[dict[str, Any]]:
    """Build template rows for each weekday."""
    label_for = day_label_fn or (lambda day: DAY_LABELS[day])
    rows: list[dict[str, Any]] = []
    for day in ordered_week_days(start_day):
        slot = menu[day]
        recipe = recipes_by_id.get(slot["recipe_id"]) if slot["recipe_id"] else None
        rows.append(
            {
                "day": day,
                "label": label_for(day),
                "recipe": recipe,
                "pinned": slot["pinned"],
                "servings": slot["servings"],
            }
        )
    return rows


def scale_ingredient_quantity(
    quantity: float, day_servings: int, recipe_servings: int
) -> float:
    """Scale an ingredient quantity from the recipe's servings to the planned servings.

    Args:
        quantity: Ingredient quantity as written in the recipe.
        day_servings: Servings the user planned for the day.
        recipe_servings: Servings the recipe is written for.

    Returns:
        The quantity needed for ``day_servings``. When ``recipe_servings`` is not
        positive the original quantity is returned unscaled.
    """
    if recipe_servings <= 0:
        return float(quantity)
    return float(quantity) * day_servings / recipe_servings


def merge_grocery_items(
    existing: list[GroceryItem], new_items: list[GroceryItem]
) -> list[GroceryItem]:
    """Combine two grocery lists, summing quantities for matching lines."""
    return build_grocery_list(existing + new_items)


def build_grocery_list(entries: list[GroceryItem]) -> list[GroceryItem]:
    """Combine ingredient entries that share the same name and unit.

    Args:
        entries: Scaled ingredient entries collected from the week menu.

    Returns:
        Aggregated grocery items sorted alphabetically by name, with quantities
        summed per (name, unit) pair and rounded to two decimals.
    """
    totals: dict[tuple[int, str, str], float] = {}
    for entry in entries:
        key = (entry["ingredient_id"], entry["name"], entry["unit"])
        totals[key] = totals.get(key, 0.0) + entry["quantity"]

    items = [
        GroceryItem(
            ingredient_id=ingredient_id,
            name=name,
            unit=unit,
            quantity=round(quantity, 2),
        )
        for (ingredient_id, name, unit), quantity in totals.items()
    ]
    return sorted(items, key=lambda item: item["name"].lower())
