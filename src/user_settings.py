"""Per-user settings persisted as JSON files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

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
    """Build the file path for one user's settings JSON file."""
    return USER_SETTINGS_DIR / f"{user_id}.json"


def _normalize_servings(value: Any) -> int:
    """Coerce a servings value to a positive integer."""
    try:
        servings = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SERVINGS
    return servings if servings >= 1 else DEFAULT_SERVINGS


def load_user_settings(user_id: int) -> UserSettings:
    """Load settings for a user, falling back to defaults when missing or invalid."""
    defaults = default_user_settings()
    path = _settings_path(user_id)
    if not path.exists():
        return defaults

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults

    language = str(data.get("language", defaults["language"])).strip()
    if not language:
        language = defaults["language"]
    servings = _normalize_servings(data.get("servings", defaults["servings"]))
    return UserSettings(language=language, servings=servings)


def save_user_settings(user_id: int, settings: UserSettings) -> None:
    """Persist one user's settings as JSON in the project root."""
    USER_SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = _settings_path(user_id)
    path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def delete_user_settings(user_id: int) -> None:
    """Delete a user's settings file when removing the account."""
    path = _settings_path(user_id)
    if path.exists():
        path.unlink()
