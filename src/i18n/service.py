"""UI translation loading, lookup, and request-scoped context."""

from contextvars import ContextVar
from litestar import Request

from src.i18n.catalog_en import TEXTS
from src.i18n.icons import apply_icons, strip_icons

DEFAULT_LANGUAGE_CODE = "en"
DUTCH_LANGUAGE_CODE = "nl"

LANGUAGE_OPTIONS: tuple[str, ...] = (
    "🇬🇧 English",
    "🇳🇱 Nederlands",
    "🇫🇷 Français",
    "🇩🇪 Deutsch",
    "🇪🇸 Español",
    "🇮🇹 Italiano",
)

LANGUAGE_OPTION_TO_CODE: dict[str, str] = {
    "🇬🇧 English": "en",
    "🇳🇱 Nederlands": "nl",
    "🇫🇷 Français": "fr",
    "🇩🇪 Deutsch": "de",
    "🇪🇸 Español": "es",
    "🇮🇹 Italiano": "it",
}

Catalog = dict[str, str]

_current_catalog: ContextVar[Catalog | None] = ContextVar(
    "current_catalog", default=None
)
_fallback_catalog: ContextVar[Catalog | None] = ContextVar(
    "fallback_catalog", default=None
)

_catalog_cache: dict[str, Catalog] = {}


def language_code_from_option(language_option: str) -> str:
    """Map a profile language display string to a language code.

    Args:
        language_option: Stored user preference such as ``🇬🇧 English``.

    Returns:
        A two-letter language code, defaulting to English when unknown.
    """
    normalized = language_option.strip()
    return LANGUAGE_OPTION_TO_CODE.get(normalized, DEFAULT_LANGUAGE_CODE)


def clear_translation_cache() -> None:
    """Clear in-memory translation catalogs (used in tests)."""
    _catalog_cache.clear()


async def load_catalog(language_code: str) -> Catalog:
    """Load a language catalog from the database with in-memory caching.

    Args:
        language_code: Two-letter language code.

    Returns:
        Mapping of translation keys to localized text.
    """
    if language_code in _catalog_cache:
        return _catalog_cache[language_code]

    from src.models import UIText

    rows = await UIText.filter(language_code=language_code).values("key", "text")
    catalog = {row["key"]: row["text"] for row in rows}
    _catalog_cache[language_code] = catalog
    return catalog


async def seed_english_texts() -> None:
    """Upsert English UI strings from ``catalog_en.TEXTS`` into the database."""
    from src.models import UIText

    for key, text in TEXTS.items():
        await UIText.update_or_create(
            defaults={"text": strip_icons(key, text)},
            language_code=DEFAULT_LANGUAGE_CODE,
            key=key,
        )
    clear_translation_cache()


async def seed_dutch_texts() -> None:
    """Upsert Dutch UI strings from ``catalog_nl.TEXTS`` into the database."""
    from src.i18n.catalog_nl import TEXTS as NL_TEXTS
    from src.models import UIText

    for key, text in NL_TEXTS.items():
        await UIText.update_or_create(
            defaults={"text": strip_icons(key, text)},
            language_code=DUTCH_LANGUAGE_CODE,
            key=key,
        )
    clear_translation_cache()


async def load_i18n_context(request: Request) -> None:
    """Load translation catalogs for the current request.

    Uses the logged-in user's language preference when available, otherwise
    English. Sets context variables used by ``t()``.

    Args:
        request: The incoming HTTP request.
    """
    from src.auth import get_current_user
    from src.user_settings import load_user_settings

    user = await get_current_user(request)
    if user is None:
        language_code = DEFAULT_LANGUAGE_CODE
    else:
        settings = await load_user_settings(user.id)
        language_code = language_code_from_option(settings["language"])

    catalog = await load_catalog(language_code)
    if language_code == DEFAULT_LANGUAGE_CODE:
        fallback = catalog
    else:
        fallback = await load_catalog(DEFAULT_LANGUAGE_CODE)

    _current_catalog.set(catalog)
    _fallback_catalog.set(fallback)


def t(key: str, **kwargs: object) -> str:
    """Look up a UI string in the current catalog with English fallback.

    Args:
        key: Dot-notation translation key.
        **kwargs: Placeholder values for ``{name}``-style interpolation.

    Returns:
        The translated string, or the key itself when no translation exists.
    """
    catalog = _current_catalog.get()
    fallback = _fallback_catalog.get()

    text: str | None = None
    if catalog is not None:
        text = catalog.get(key)
    if text is None and fallback is not None:
        text = fallback.get(key)
    if text is None:
        text = TEXTS.get(key, key)

    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return apply_icons(key, text)
