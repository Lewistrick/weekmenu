"""Detect and convert ingredients that use multiple measurement units."""

from dataclasses import dataclass
from itertools import combinations
from typing import cast

from loguru import logger

from src.i18n.service import t
from src.models import (
    GroceryListItem,
    Ingredient,
    RecipeIngredient,
    Unit,
    WeeklyGrocery,
)


@dataclass(frozen=True, slots=True)
class UnitSummary:
    """A unit label for display on the merge-units page."""

    id: int
    abbrev: str
    label: str


@dataclass(frozen=True, slots=True)
class IngredientUnitPairRow:
    """One ingredient shown with two distinct units used across lists."""

    ingredient_id: int
    ingredient_name: str
    unit_a: UnitSummary
    unit_b: UnitSummary

    @property
    def row_id(self) -> str:
        """Stable DOM id for HTMX row targeting."""
        return f"merge-pair-{self.ingredient_id}-{self.unit_a.id}-{self.unit_b.id}"


@dataclass(frozen=True)
class IngredientUnitConversionResult:
    """Outcome of converting one ingredient unit to another."""

    ok: bool
    error_message: str = ""
    recipe_ids: tuple[int, ...] = ()
    source_unit_label: str = ""
    target_unit_label: str = ""
    list_lines_converted: int = 0


def _unit_display_label(unit: Unit) -> str:
    """Return a unit label for user-facing messages."""
    return f"{_unit_label(unit)} ({unit.abbrev})"


def _unit_label(unit: Unit) -> str:
    """Return the best display label for a unit."""
    if unit.single:
        return unit.single
    return unit.abbrev


def _unit_summary(unit: Unit) -> UnitSummary:
    """Build a display summary for a unit row."""
    return UnitSummary(id=unit.id, abbrev=unit.abbrev, label=_unit_label(unit))


def _as_int_list(values: object) -> list[int]:
    """Coerce ORM flat values_list results to integers for type checking."""
    result: list[int] = []
    for value in cast(list[object], values):
        if value is None:
            continue
        result.append(int(cast(int, value)))
    return result


async def _collect_unit_ids(
    owner_id: int,
    ingredient_id: int,
    *,
    include_grocery_list: bool = True,
) -> set[int]:
    """Return unit ids used for an ingredient across recipes and lists.

    Args:
        owner_id: The logged-in user's id.
        ingredient_id: Ingredient to inspect.
        include_grocery_list: When ``False``, ignore persisted grocery list
            lines. Used when listing merge candidates so stale list state does
            not surface units that are not used in recipes or weekly groceries.
    """
    unit_ids: set[int] = set()

    unit_ids.update(
        _as_int_list(
            await RecipeIngredient.filter(
                ingredient_id=ingredient_id,
                recipe__owner_id=owner_id,
            ).values_list("unit_id", flat=True)
        )
    )

    unit_ids.update(
        _as_int_list(
            await WeeklyGrocery.filter(
                owner_id=owner_id,
                ingredient_id=ingredient_id,
            ).values_list("unit_id", flat=True)
        )
    )

    if include_grocery_list:
        unit_ids.update(
            _as_int_list(
                await GroceryListItem.filter(
                    user_id=owner_id,
                    ingredient_id=ingredient_id,
                ).values_list("unit_id", flat=True)
            )
        )

    return unit_ids


async def load_multi_unit_pairs(owner_id: int) -> list[IngredientUnitPairRow]:
    """List ingredient/unit pairs where an ingredient uses more than one unit.

    Only units that appear in recipes or weekly groceries count. Grocery list
    lines are ignored because they do not cause duplicate grocery generation.

    Args:
        owner_id: The logged-in user's id.

    Returns:
        Sorted rows with one entry per unordered unit pair per ingredient.
    """
    ingredient_ids = set(
        _as_int_list(
            await RecipeIngredient.filter(recipe__owner_id=owner_id).values_list(
                "ingredient_id",
                flat=True,
            )
        )
    )
    ingredient_ids.update(
        _as_int_list(
            await WeeklyGrocery.filter(owner_id=owner_id).values_list(
                "ingredient_id",
                flat=True,
            )
        )
    )

    rows: list[IngredientUnitPairRow] = []
    for ingredient_id in ingredient_ids:
        unit_ids = await _collect_unit_ids(
            owner_id, ingredient_id, include_grocery_list=False
        )
        if len(unit_ids) < 2:
            continue

        ingredient = await Ingredient.get_or_none(id=ingredient_id, owner_id=owner_id)
        if ingredient is None:
            continue

        units = await Unit.filter(id__in=unit_ids, owner_id=owner_id).order_by("abbrev")
        unit_summaries = [_unit_summary(unit) for unit in units]
        for unit_a, unit_b in combinations(unit_summaries, 2):
            first, second = (
                (unit_a, unit_b) if unit_a.id < unit_b.id else (unit_b, unit_a)
            )
            rows.append(
                IngredientUnitPairRow(
                    ingredient_id=ingredient.id,
                    ingredient_name=ingredient.name,
                    unit_a=first,
                    unit_b=second,
                )
            )

    rows.sort(
        key=lambda row: (
            row.ingredient_name.lower(),
            row.unit_a.abbrev,
            row.unit_b.abbrev,
        )
    )
    return rows


async def log_pair_usage_for_edit(owner_id: int, pair: IngredientUnitPairRow) -> None:
    """Log recipe usages per unit when opening the inline conversion form.

    Args:
        owner_id: The logged-in user's id.
        pair: Ingredient/unit pair being edited.
    """
    logger.debug(
        "Merge units edit for ingredient {} (id={})",
        pair.ingredient_name,
        pair.ingredient_id,
    )
    for unit in (pair.unit_a, pair.unit_b):
        unit_name = f"{unit.label} ({unit.abbrev})"
        recipe_rows = await RecipeIngredient.filter(
            ingredient_id=pair.ingredient_id,
            unit_id=unit.id,
            recipe__owner_id=owner_id,
        ).select_related("recipe")
        if not recipe_rows:
            logger.debug("{} - (no recipes)", unit_name)
        for row in recipe_rows:
            logger.debug(
                "{} - /recipes/view/{} - {}",
                unit_name,
                row.recipe.id,
                row.recipe.name,
            )
        weekly_rows = await WeeklyGrocery.filter(
            owner_id=owner_id,
            ingredient_id=pair.ingredient_id,
            unit_id=unit.id,
        )
        for weekly_row in weekly_rows:
            logger.debug(
                "{} - weekly grocery - quantity {}",
                unit_name,
                weekly_row.quantity,
            )


async def _get_pair_row(
    owner_id: int,
    ingredient_id: int,
    unit_a_id: int,
    unit_b_id: int,
) -> IngredientUnitPairRow | None:
    """Return a pair row when the ingredient still uses both units."""
    if unit_a_id == unit_b_id:
        return None

    ingredient = await Ingredient.get_or_none(id=ingredient_id, owner_id=owner_id)
    if ingredient is None:
        return None

    unit_a = await Unit.get_or_none(id=unit_a_id, owner_id=owner_id)
    unit_b = await Unit.get_or_none(id=unit_b_id, owner_id=owner_id)
    if unit_a is None or unit_b is None:
        return None

    unit_ids = await _collect_unit_ids(
        owner_id, ingredient_id, include_grocery_list=False
    )
    if unit_a_id not in unit_ids or unit_b_id not in unit_ids:
        return None

    first, second = sorted((unit_a, unit_b), key=lambda unit: unit.id)
    return IngredientUnitPairRow(
        ingredient_id=ingredient.id,
        ingredient_name=ingredient.name,
        unit_a=_unit_summary(first),
        unit_b=_unit_summary(second),
    )


async def _convert_recipe_ingredients(
    owner_id: int,
    ingredient_id: int,
    source_unit_id: int,
    target_unit_id: int,
    multiplier: float,
) -> list[int]:
    """Convert recipe ingredient lines from source unit to target unit."""
    recipe_ids: set[int] = set()
    source_rows = await RecipeIngredient.filter(
        ingredient_id=ingredient_id,
        unit_id=source_unit_id,
        recipe__owner_id=owner_id,
    ).select_related("recipe")
    for row in source_rows:
        new_quantity = row.quantity * multiplier
        recipe_id = row.recipe.id
        existing = await RecipeIngredient.get_or_none(
            recipe_id=recipe_id,
            ingredient_id=ingredient_id,
            unit_id=target_unit_id,
        )
        if existing is not None:
            existing.quantity += new_quantity
            await existing.save()
            await row.delete()
        else:
            row.unit_id = target_unit_id
            row.quantity = new_quantity
            await row.save()
        recipe_ids.add(recipe_id)
    return sorted(recipe_ids)


async def _convert_weekly_groceries(
    owner_id: int,
    ingredient_id: int,
    source_unit_id: int,
    target_unit_id: int,
    multiplier: float,
) -> int:
    """Convert weekly grocery lines from source unit to target unit."""
    converted = 0
    source_rows = await WeeklyGrocery.filter(
        owner_id=owner_id,
        ingredient_id=ingredient_id,
        unit_id=source_unit_id,
    )
    for row in source_rows:
        new_quantity = row.quantity * multiplier
        existing = await WeeklyGrocery.get_or_none(
            owner_id=owner_id,
            ingredient_id=ingredient_id,
            unit_id=target_unit_id,
        )
        if existing is not None:
            existing.quantity += new_quantity
            await existing.save()
            await row.delete()
        else:
            row.unit_id = target_unit_id
            row.quantity = new_quantity
            await row.save()
        converted += 1
    return converted


async def _convert_grocery_list_items(
    owner_id: int,
    ingredient_id: int,
    source_unit_id: int,
    target_unit_id: int,
    multiplier: float,
) -> int:
    """Convert grocery list lines from source unit to target unit."""
    converted = 0
    source_rows = await GroceryListItem.filter(
        user_id=owner_id,
        ingredient_id=ingredient_id,
        unit_id=source_unit_id,
    )
    for row in source_rows:
        new_quantity = row.quantity * multiplier
        existing = await GroceryListItem.get_or_none(
            user_id=owner_id,
            ingredient_id=ingredient_id,
            unit_id=target_unit_id,
        )
        if existing is not None:
            existing.quantity += new_quantity
            await existing.save()
            await row.delete()
        else:
            row.unit_id = target_unit_id
            row.quantity = new_quantity
            await row.save()
        converted += 1
    return converted


def _conversion_multiplier(
    pair: IngredientUnitPairRow,
    *,
    source_unit_id: int,
    target_unit_id: int,
    amount_a: float,
    amount_b: float,
) -> float:
    """Return the quantity multiplier from source unit to target unit.

    The ratio is defined as ``amount_a [unit_a] = amount_b [unit_b]``.
    """
    if source_unit_id == pair.unit_a.id and target_unit_id == pair.unit_b.id:
        return amount_b / amount_a
    if source_unit_id == pair.unit_b.id and target_unit_id == pair.unit_a.id:
        return amount_a / amount_b
    raise ValueError("source and target units do not match the selected pair")


async def convert_ingredient_unit(
    owner_id: int,
    ingredient_id: int,
    unit_a_id: int,
    unit_b_id: int,
    *,
    target_unit_id: int,
    amount_a: float,
    amount_b: float,
) -> IngredientUnitConversionResult:
    """Convert one unit to another for an ingredient across recipes and lists.

    The conversion is defined as ``amount_a [unit_a] = amount_b [unit_b]``.
    Quantities in the source unit are multiplied by the derived ratio to obtain
    target-unit quantities. When a recipe or list already contains the target
    unit, amounts are merged.

    Args:
        owner_id: The logged-in user's id.
        ingredient_id: Ingredient to update.
        unit_a_id: First unit id from the selected pair.
        unit_b_id: Second unit id from the selected pair.
        target_unit_id: Unit to keep after conversion.
        amount_a: Amount for ``unit_a`` in the conversion ratio.
        amount_b: Amount for ``unit_b`` in the conversion ratio.

    Returns:
        A structured result with edited recipe ids and unit labels on success.
    """
    pair = await _get_pair_row(owner_id, ingredient_id, unit_a_id, unit_b_id)
    if pair is None:
        return IngredientUnitConversionResult(
            ok=False,
            error_message=t("message.ingredient_units.not_found"),
        )

    pair_unit_ids = {pair.unit_a.id, pair.unit_b.id}
    if target_unit_id not in pair_unit_ids:
        return IngredientUnitConversionResult(
            ok=False,
            error_message=t("message.ingredient_units.invalid_target_unit"),
        )

    source_unit_id = (
        pair.unit_b.id if target_unit_id == pair.unit_a.id else pair.unit_a.id
    )
    if amount_a <= 0 or amount_b <= 0:
        return IngredientUnitConversionResult(
            ok=False,
            error_message=t("message.ingredient_units.invalid_amounts"),
        )

    try:
        multiplier = _conversion_multiplier(
            pair,
            source_unit_id=source_unit_id,
            target_unit_id=target_unit_id,
            amount_a=amount_a,
            amount_b=amount_b,
        )
    except ValueError:
        return IngredientUnitConversionResult(
            ok=False,
            error_message=t("message.ingredient_units.invalid_target_unit"),
        )

    source_unit = await Unit.get_or_none(id=source_unit_id, owner_id=owner_id)
    target_unit = await Unit.get_or_none(id=target_unit_id, owner_id=owner_id)
    if source_unit is None or target_unit is None:
        return IngredientUnitConversionResult(
            ok=False,
            error_message=t("message.ingredient_units.not_found"),
        )

    recipe_ids = await _convert_recipe_ingredients(
        owner_id,
        ingredient_id,
        source_unit_id,
        target_unit_id,
        multiplier,
    )
    weekly_count = await _convert_weekly_groceries(
        owner_id,
        ingredient_id,
        source_unit_id,
        target_unit_id,
        multiplier,
    )
    grocery_count = await _convert_grocery_list_items(
        owner_id,
        ingredient_id,
        source_unit_id,
        target_unit_id,
        multiplier,
    )

    list_lines_converted = weekly_count + grocery_count
    if not recipe_ids and list_lines_converted == 0:
        return IngredientUnitConversionResult(
            ok=False,
            error_message=t("message.ingredient_units.nothing_to_convert"),
        )

    return IngredientUnitConversionResult(
        ok=True,
        recipe_ids=tuple(recipe_ids),
        source_unit_label=_unit_display_label(source_unit),
        target_unit_label=_unit_display_label(target_unit),
        list_lines_converted=list_lines_converted,
    )
