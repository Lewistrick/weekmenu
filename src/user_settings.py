"""Per-user settings persisted in the database."""

import json
from pathlib import Path
from typing import Any, TypedDict

from src.plan_store import ensure_user_preference, migrate_json_user_settings

DEFAULT_LANGUAGE = "🇬🇧 English"
DEFAULT_SERVINGS = 2
USER_SETTINGS_DIR = Path("user_settings")


class UserSettings(TypedDict):
    """User-adjustable profile settings."""

    language: str
    servings: int


def default_user_settings() -> UserSettings:
    """Return default settings for a new or missing user settings file."""
    return UserSettings(language=DEFAULT_LANGUAGE, servings=DEFAULT_SERVINGS)


def _settings_path(user_id: int) -> Path:
    """Build the file path for one user's legacy settings JSON file."""
    return USER_SETTINGS_DIR / f"{user_id}.json"


def _normalize_servings(value: Any) -> int:
    """Coerce a servings value to a positive integer."""
    try:
        servings = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SERVINGS
    return servings if servings >= 1 else DEFAULT_SERVINGS


def _load_legacy_json_settings(user_id: int) -> UserSettings | None:
    """Load settings from a legacy JSON file when present."""
    path = _settings_path(user_id)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    defaults = default_user_settings()
    language = str(data.get("language", defaults["language"])).strip()
    if not language:
        language = defaults["language"]
    servings = _normalize_servings(data.get("servings", defaults["servings"]))
    return UserSettings(language=language, servings=servings)


async def load_user_settings(user_id: int) -> UserSettings:
    """Load settings for a user, migrating legacy JSON files when needed."""
    legacy = _load_legacy_json_settings(user_id)
    if legacy is not None:
        await migrate_json_user_settings(
            user_id,
            language=legacy["language"],
            servings=legacy["servings"],
        )
        delete_user_settings(user_id)

    preference = await ensure_user_preference(user_id)
    language = preference.language.strip() or DEFAULT_LANGUAGE
    servings = _normalize_servings(preference.default_servings)
    return UserSettings(language=language, servings=servings)


async def save_user_settings(user_id: int, settings: UserSettings) -> None:
    """Persist one user's settings in the database."""
    preference = await ensure_user_preference(user_id)
    language = str(settings["language"]).strip() or DEFAULT_LANGUAGE
    preference.language = language
    preference.default_servings = _normalize_servings(settings["servings"])
    await preference.save()
    delete_user_settings(user_id)


def delete_user_settings(user_id: int) -> None:
    """Delete a user's legacy settings file when removing the account."""
    path = _settings_path(user_id)
    if path.exists():
        path.unlink()
