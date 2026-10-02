"""Default emoji for shelves (ingredient categories), suggested from the name.

Kept free of app imports so the database start-up code can use it.
"""

# Lowercase keyword (EN and NL) -> emoji. The first keyword found in a shelf
# name wins, so more specific words come first ("vlees" before "vis" for
# "Vlees & vis").
ICON_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("groente", "🥦"),
    ("vegetable", "🥦"),
    ("fruit", "🍎"),
    ("vlees", "🥩"),
    ("meat", "🥩"),
    ("vis", "🐟"),
    ("fish", "🐟"),
    ("eiwit", "🫘"),
    ("protein", "🫘"),
    ("zuivel", "🧀"),
    ("dairy", "🧀"),
    ("kruid", "🌿"),
    ("specerij", "🌿"),
    ("herb", "🌿"),
    ("spice", "🌿"),
    ("brood", "🍞"),
    ("bread", "🍞"),
    ("bakery", "🍞"),
    ("vriez", "🧊"),
    ("vries", "🧊"),
    ("freez", "🧊"),
    ("frozen", "🧊"),
    ("sauz", "🫙"),
    ("saus", "🫙"),
    ("sauce", "🫙"),
    ("condiment", "🫙"),
    ("voorraad", "🥫"),
    ("pantry", "🥫"),
    ("drank", "🥤"),
    ("drink", "🥤"),
    ("overig", "📦"),
    ("other", "📦"),
)


def suggest_icon(name: str) -> str:
    """Return the emoji for the first keyword in ``name``, or ``""``."""
    lowered = name.lower()
    for keyword, icon in ICON_KEYWORDS:
        if keyword in lowered:
            return icon
    return ""


def icon_backfill_sql() -> str:
    """SQL that gives every shelf without an icon its suggested emoji.

    Works on SQLite and PostgreSQL. Shelves matching no keyword keep ``""``.
    """
    cases = "\n".join(
        f"    WHEN lower(\"name\") LIKE '%{keyword}%' THEN '{icon}'"
        for keyword, icon in ICON_KEYWORDS
    )
    return (
        'UPDATE "ingredientcategory" SET "icon" = CASE\n'
        f"{cases}\n"
        "    ELSE '' END\n"
        "WHERE \"icon\" = '';"
    )
