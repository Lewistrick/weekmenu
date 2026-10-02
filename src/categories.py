"""Per-user ingredient categories (vegetables, freezer, ...).

Every ingredient can have one category. Lists group their items by category in
the user's chosen order, so shopping goes one shop section at a time and
checking the cupboards goes one drawer at a time.
"""

from collections.abc import Mapping, Sequence
from typing import Any, TypedDict

from src.category_icons import suggest_icon
from src.i18n.service import t
from src.models import Ingredient, IngredientCategory
from src.plan_store import ensure_user_preference

# Starter set seeded for each user, in shopping order. Names come from the
# catalog in the user's language at seeding time, then belong to the user.
DEFAULT_CATEGORY_KEYS: tuple[str, ...] = (
    "categories.default.vegetables",
    "categories.default.fruit",
    "categories.default.meat_fish",
    "categories.default.proteins",
    "categories.default.dairy_eggs",
    "categories.default.herbs_spices",
    "categories.default.pantry",
    "categories.default.freezer",
    "categories.default.other",
)

# Longest icon accepted: room for one emoji, including multi-code-point ones
# such as flags or skin-tone and ZWJ sequences.
MAX_ICON_LENGTH = 16


class CategoryInfo(TypedDict):
    """A category prepared for templates."""

    id: int
    name: str
    icon: str
    # What chips show: the icon, or the name's first letter when it has none.
    badge: str
    sort_order: int
    ingredient_count: int


class CategorySection(TypedDict):
    """A run of list items that share a category, with its heading."""

    category_id: int | None
    name: str
    icon: str
    entries: list[Any]


class AssignmentRow(TypedDict):
    """One ingredient on the categories page."""

    id: int
    name: str
    category_id: int | None


class AssignmentGroup(TypedDict):
    """Ingredients that currently share a category (or have none)."""

    category: CategoryInfo | None
    rows: list[AssignmentRow]


def _first_letter(name: str) -> str:
    """Return a category's first letter, for chips when it has no icon."""
    stripped = name.strip()
    return stripped[0].upper() if stripped else "?"


def _clean_icon(icon: Any) -> str | None:
    """Return a stripped icon, or ``None`` when it is too long to be one emoji."""
    clean = str(icon or "").strip()
    return clean if len(clean) <= MAX_ICON_LENGTH else None


async def load_categories(owner_id: int) -> list[CategoryInfo]:
    """Return a user's categories in their chosen order."""
    rows = await IngredientCategory.filter(owner_id=owner_id).order_by(
        "sort_order", "id"
    )
    counts: dict[int, int] = {}
    for category_id in await Ingredient.filter(
        owner_id=owner_id, category_id__isnull=False
    ).values_list("category_id", flat=True):
        counts[int(category_id)] = counts.get(int(category_id), 0) + 1  # ty: ignore[invalid-argument-type]
    return [
        CategoryInfo(
            id=row.id,
            name=row.name,
            icon=row.icon,
            badge=row.icon or _first_letter(row.name),
            sort_order=row.sort_order,
            ingredient_count=counts.get(row.id, 0),
        )
        for row in rows
    ]


async def ensure_default_categories(owner_id: int) -> int:
    """Seed the starter categories once per user.

    A preference flag records that seeding happened, so a user who deletes
    every category does not get the starter set back.

    Returns:
        The number of categories created.
    """
    preference = await ensure_user_preference(owner_id)
    if preference.categories_seeded:
        return 0
    created = 0
    if not await IngredientCategory.filter(owner_id=owner_id).exists():
        for index, key in enumerate(DEFAULT_CATEGORY_KEYS):
            name = t(key)
            await IngredientCategory.create(
                owner_id=owner_id,
                name=name,
                icon=suggest_icon(name),
                sort_order=index,
            )
            created += 1
    preference.categories_seeded = True
    await preference.save()
    return created


async def _name_taken(
    owner_id: int, name: str, *, exclude_id: int | None = None
) -> bool:
    """Return whether another category of this user has the name (any case)."""
    query = IngredientCategory.filter(owner_id=owner_id)
    if exclude_id is not None:
        query = query.exclude(id=exclude_id)
    existing = await query.values_list("name", flat=True)
    return name.casefold() in {str(other).casefold() for other in existing}


async def add_category(owner_id: int, name: Any, icon: Any = "") -> tuple[bool, str]:
    """Add a category at the end of the user's order.

    An empty icon gets one suggested from the name (see ``suggest_icon``).

    Returns:
        A success flag and a message describing the outcome.
    """
    clean = str(name or "").strip()
    clean_icon = _clean_icon(icon)
    if not clean:
        return False, t("message.categories.name_required")
    if clean_icon is None:
        return False, t("message.categories.icon_too_long")
    if await _name_taken(owner_id, clean):
        return False, t("message.categories.already_exists", name=clean)
    last = (
        await IngredientCategory.filter(owner_id=owner_id)
        .order_by("-sort_order")
        .first()
    )
    await IngredientCategory.create(
        owner_id=owner_id,
        name=clean,
        icon=clean_icon or suggest_icon(clean),
        sort_order=(last.sort_order + 1) if last is not None else 0,
    )
    return True, t("message.categories.added", name=clean)


async def update_category(
    owner_id: int, category_id: int, name: Any, icon: Any = ""
) -> tuple[bool, str]:
    """Rename an owned category and set its icon (empty = first letter).

    Returns:
        A success flag and a message describing the outcome.
    """
    row = await IngredientCategory.get_or_none(id=category_id, owner_id=owner_id)
    if row is None:
        return False, t("message.categories.not_found")
    clean = str(name or "").strip()
    clean_icon = _clean_icon(icon)
    if not clean:
        return False, t("message.categories.name_required")
    if clean_icon is None:
        return False, t("message.categories.icon_too_long")
    if await _name_taken(owner_id, clean, exclude_id=category_id):
        return False, t("message.categories.already_exists", name=clean)
    row.name = clean
    row.icon = clean_icon
    await row.save()
    return True, t("message.categories.updated", name=clean)


async def reorder_categories(owner_id: int, category_ids: Sequence[int]) -> bool:
    """Store a new order for all of a user's categories.

    Args:
        owner_id: The user whose categories are reordered.
        category_ids: Every one of the user's category ids, in the new order.

    Returns:
        ``True`` when saved; ``False`` when the ids are not exactly the user's
        categories (e.g. a stale page after a category was added or deleted).
    """
    rows = {row.id: row for row in await IngredientCategory.filter(owner_id=owner_id)}
    if len(category_ids) != len(rows) or set(category_ids) != set(rows):
        return False
    for position, category_id in enumerate(category_ids):
        row = rows[category_id]
        if row.sort_order != position:
            row.sort_order = position
            await row.save()
    return True


async def delete_category(owner_id: int, category_id: int) -> bool:
    """Delete an owned category; its ingredients become uncategorised.

    Returns:
        ``True`` when a category was deleted.
    """
    row = await IngredientCategory.get_or_none(id=category_id, owner_id=owner_id)
    if row is None:
        return False
    await Ingredient.filter(owner_id=owner_id, category_id=category_id).update(
        category_id=None
    )
    await row.delete()
    return True


async def set_ingredient_category(
    owner_id: int, ingredient_id: int, category_id: int | None
) -> bool:
    """Assign (or clear, with ``None``) an owned ingredient's category.

    Returns:
        ``True`` when the ingredient and category both belong to the user.
    """
    ingredient = await Ingredient.get_or_none(id=ingredient_id, owner_id=owner_id)
    if ingredient is None:
        return False
    if (
        category_id is not None
        and not await IngredientCategory.filter(
            id=category_id, owner_id=owner_id
        ).exists()
    ):
        return False
    await Ingredient.filter(id=ingredient_id).update(category_id=category_id)
    return True


async def load_ingredient_category_ids(owner_id: int) -> dict[int, int | None]:
    """Map each of a user's ingredient ids to its category id (or ``None``)."""
    rows = await Ingredient.filter(owner_id=owner_id).values_list("id", "category_id")
    return {
        int(ingredient_id): int(category_id) if category_id is not None else None
        for ingredient_id, category_id in rows
    }


async def load_assignment_groups(
    owner_id: int, categories: list[CategoryInfo]
) -> list[AssignmentGroup]:
    """Return the user's ingredients grouped by category, uncategorised first."""
    ingredients = await Ingredient.filter(owner_id=owner_id).order_by("name")
    category_ids = await load_ingredient_category_ids(owner_id)
    rows = [
        AssignmentRow(
            id=ingredient.id,
            name=ingredient.name,
            category_id=category_ids.get(ingredient.id),
        )
        for ingredient in ingredients
    ]
    groups: list[AssignmentGroup] = []
    uncategorised = [row for row in rows if row["category_id"] is None]
    if uncategorised:
        groups.append(AssignmentGroup(category=None, rows=uncategorised))
    for category in categories:
        members = [row for row in rows if row["category_id"] == category["id"]]
        if members:
            groups.append(AssignmentGroup(category=category, rows=members))
    return groups


def group_by_category(
    items: Sequence[Mapping[str, Any]],
    ingredient_category_ids: Mapping[int, int | None],
    categories: Sequence[CategoryInfo],
    *,
    uncategorised_label: str,
    always: bool = False,
) -> list[CategorySection]:
    """Split list items into category sections in the user's order.

    Items keep their relative order within a section; uncategorised items come
    last. Each item needs an ``ingredient_id`` key.

    Args:
        items: Grocery or inventory rows.
        ingredient_category_ids: Ingredient id to category id.
        categories: The user's categories, in order.
        uncategorised_label: Heading for items without a category.
        always: Return sections even when no item has a category.

    Returns:
        Non-empty sections, or ``[]`` when no item is categorised (and
        ``always`` is false), meaning the caller shows a flat list.
    """
    known = {category["id"] for category in categories}
    buckets: dict[int | None, list[Any]] = {}
    for item in items:
        category_id = ingredient_category_ids.get(item["ingredient_id"])
        if category_id not in known:
            category_id = None
        buckets.setdefault(category_id, []).append(item)
    if not always and set(buckets) <= {None}:
        return []
    sections = [
        CategorySection(
            category_id=category["id"],
            name=category["name"],
            icon=category["icon"],
            entries=buckets[category["id"]],
        )
        for category in categories
        if category["id"] in buckets
    ]
    if None in buckets:
        sections.append(
            CategorySection(
                category_id=None,
                name=uncategorised_label,
                icon="",
                entries=buckets[None],
            )
        )
    return sections
