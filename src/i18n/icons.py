"""Language-independent UI icons keyed by translation key."""

from __future__ import annotations

KEY_PREFIX_ICONS: dict[str, str] = {
    "nav.week_menu": "🗓️ ",
    "nav.grocery_list": "🛒 ",
    "nav.recipes": "🍽️ ",
    "nav.find_recipe": "🔎 ",
    "nav.add_recipe": "➕ ",
    "nav.random_private_recipe": "🎲 ",
    "nav.random_public_recipe": "🌍 ",
    "nav.missing_tags": "🏷️ ",
    "nav.settings": "⚙️ ",
    "nav.tag_groups": "🏷️ ",
    "nav.shops": "🏪 ",
    "nav.week_menu_constraints": "🎛️ ",
    "nav.weekly_groceries": "🧺 ",
    "nav.units": "📏 ",
    "nav.merge_ingredient_units": "🔀 ",
    "nav.merge_ingredients": "🔗 ",
    "nav.account": "👤 ",
    "nav.logout": "🚪 ",
    "recipe.edit.back_to_view": "← ",
    "recipe.edit.action.edit_title": "✏️ ",
    "recipe.edit.action.edit_description": "✏️ ",
    "recipe.edit.action.save_tags": "💾 ",
    "recipes_missing_tags.action.save": "💾 ",
    "recipes_missing_tags.action.cancel": "✕ ",
    "recipe.edit.action.delete": "🗑️ ",
    "recipe.view.action.edit": "✏️ ",
    "recipe.view.action.import": "📥 ",
    "recipe.view.action.add_to_week_menu": "🗓️ ",
    "week_menu.action.randomize": "🎲 ",
    "week_menu.constraints.manage_button": "🎛️ ",
    "week_menu.constraints.save": "💾 ",
    "grocery.back_to_week_menu": "← ",
    "grocery.action.add_weekly_groceries": "🧺 ",
    "grocery.generate.replace": "🔄 ",
    "grocery.generate.add": "➕ ",
    "weekly_groceries.back_to_grocery_list": "🛒 ",
}

KEY_SUFFIX_ICONS: dict[str, str] = {}


def apply_icons(key: str, text: str) -> str:
    """Prepend and append hardcoded icons for a translation key.

    Args:
        key: Dot-notation translation key.
        text: Localized text without icons.

    Returns:
        Text with language-independent icons applied when configured.
    """
    prefix = KEY_PREFIX_ICONS.get(key, "")
    suffix = KEY_SUFFIX_ICONS.get(key, "")
    return f"{prefix}{text}{suffix}"


def strip_icons(key: str, text: str) -> str:
    """Remove configured icons from text before storing in the database.

    Args:
        key: Dot-notation translation key.
        text: Text that may still include icons from legacy catalogs.

    Returns:
        Text without configured prefix or suffix icons.
    """
    prefix = KEY_PREFIX_ICONS.get(key, "")
    suffix = KEY_SUFFIX_ICONS.get(key, "")
    if prefix and text.startswith(prefix):
        text = text[len(prefix) :]
    if suffix and text.endswith(suffix):
        text = text[: -len(suffix)]
    return text
