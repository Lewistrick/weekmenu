"""Admin translation catalog helpers: list, filter, group, and save UIText rows."""

from dataclasses import dataclass, field
from typing import Any

from src.i18n.catalog_en import TEXTS as EN_TEXTS
from src.i18n.service import (
    DEFAULT_LANGUAGE_CODE,
    DUTCH_LANGUAGE_CODE,
    LANGUAGE_OPTION_TO_CODE,
    LANGUAGE_OPTIONS,
    clear_translation_cache,
)
from src.models import UIText

CODE_TO_LANGUAGE_OPTION: dict[str, str] = {
    code: option for option, code in LANGUAGE_OPTION_TO_CODE.items()
}


@dataclass
class TranslationRow:
    """One editable UIText key with English and selected-language values."""

    key: str
    english_text: str
    selected_text: str
    incomplete: bool


@dataclass
class TranslationTreeNode:
    """A hierarchical group or leaf in the translations list."""

    name: str
    path: str
    depth: int
    children: list["TranslationTreeNode"] = field(default_factory=list)
    row: TranslationRow | None = None


def language_choices() -> list[dict[str, str]]:
    """Return language options for the translations editor dropdown."""
    return [
        {"code": LANGUAGE_OPTION_TO_CODE[option], "label": option}
        for option in LANGUAGE_OPTIONS
        if LANGUAGE_OPTION_TO_CODE[option] != DEFAULT_LANGUAGE_CODE
    ]


def normalize_language_code(language_code: str | None) -> str:
    """Return a known language code, defaulting to Dutch."""
    if language_code and language_code in CODE_TO_LANGUAGE_OPTION:
        if language_code == DEFAULT_LANGUAGE_CODE:
            return DUTCH_LANGUAGE_CODE
        return language_code
    return DUTCH_LANGUAGE_CODE


async def load_translation_maps(
    language_code: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Load English and selected-language text maps keyed by UI string key."""
    english_rows = await UIText.filter(language_code=DEFAULT_LANGUAGE_CODE).values(
        "key", "text"
    )
    selected_rows = await UIText.filter(language_code=language_code).values(
        "key", "text"
    )
    english = {row["key"]: row["text"] for row in english_rows}
    for key, text in EN_TEXTS.items():
        english.setdefault(key, text)
    selected = {row["key"]: row["text"] for row in selected_rows}
    return english, selected


def all_translation_keys(
    english: dict[str, str], selected: dict[str, str]
) -> list[str]:
    """Return sorted unique keys from catalogs and database maps."""
    return sorted(set(english) | set(selected) | set(EN_TEXTS))


def top_level_groups(keys: list[str]) -> list[str]:
    """Return sorted unique first key segments for filter checkboxes."""
    return sorted({key.split(".", 1)[0] for key in keys if key})


def filter_translation_rows(
    keys: list[str],
    english: dict[str, str],
    selected: dict[str, str],
    *,
    groups: set[str] | None = None,
    search: str = "",
    incomplete_only: bool = False,
) -> list[TranslationRow]:
    """Filter keys into editable translation rows."""
    needle = search.strip().casefold()
    rows: list[TranslationRow] = []
    for key in keys:
        top = key.split(".", 1)[0]
        if groups and top not in groups:
            continue
        english_text = english.get(key, "")
        selected_text = selected.get(key, "")
        incomplete = not selected_text.strip()
        if incomplete_only and not incomplete:
            continue
        if needle:
            haystacks = (key, english_text, selected_text)
            if not any(needle in value.casefold() for value in haystacks):
                continue
        rows.append(
            TranslationRow(
                key=key,
                english_text=english_text,
                selected_text=selected_text,
                incomplete=incomplete,
            )
        )
    return rows


def build_translation_tree(rows: list[TranslationRow]) -> list[TranslationTreeNode]:
    """Build a nested group tree from filtered translation rows."""
    root_children: dict[str, Any] = {}

    for row in rows:
        parts = row.key.split(".")
        cursor = root_children
        path_parts: list[str] = []
        for index, part in enumerate(parts):
            path_parts.append(part)
            path = ".".join(path_parts)
            is_leaf = index == len(parts) - 1
            if part not in cursor:
                cursor[part] = {
                    "name": part,
                    "path": path,
                    "depth": index,
                    "children": {},
                    "row": row if is_leaf else None,
                }
            elif is_leaf:
                cursor[part]["row"] = row
            cursor = cursor[part]["children"]

    def to_nodes(nodes: dict[str, Any]) -> list[TranslationTreeNode]:
        """Convert nested dicts into typed tree nodes sorted by name."""
        result: list[TranslationTreeNode] = []
        for name in sorted(nodes):
            data = nodes[name]
            result.append(
                TranslationTreeNode(
                    name=data["name"],
                    path=data["path"],
                    depth=data["depth"],
                    children=to_nodes(data["children"]),
                    row=data["row"],
                )
            )
        return result

    return to_nodes(root_children)


async def list_translation_tree(
    *,
    language_code: str,
    groups: set[str] | None = None,
    search: str = "",
    incomplete_only: bool = False,
) -> tuple[list[str], list[TranslationTreeNode]]:
    """Return top-level group names and a filtered hierarchical tree."""
    english, selected = await load_translation_maps(language_code)
    keys = all_translation_keys(english, selected)
    tops = top_level_groups(keys)
    rows = filter_translation_rows(
        keys,
        english,
        selected,
        groups=groups,
        search=search,
        incomplete_only=incomplete_only,
    )
    return tops, build_translation_tree(rows)


async def save_translation_texts(
    key: str,
    *,
    english_text: str,
    selected_language: str,
    selected_text: str,
) -> TranslationRow:
    """Upsert English and selected-language texts for one key."""
    normalized_key = key.strip()
    language_code = normalize_language_code(selected_language)
    english_value = english_text.strip()
    selected_value = selected_text.strip()

    await UIText.update_or_create(
        defaults={"text": english_value},
        language_code=DEFAULT_LANGUAGE_CODE,
        key=normalized_key,
    )
    await UIText.update_or_create(
        defaults={"text": selected_value},
        language_code=language_code,
        key=normalized_key,
    )
    clear_translation_cache()
    return TranslationRow(
        key=normalized_key,
        english_text=english_value,
        selected_text=selected_value,
        incomplete=not selected_value,
    )
