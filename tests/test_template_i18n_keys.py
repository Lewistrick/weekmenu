"""Guard against templates referencing translation keys that do not exist.

This catches a recurring bug where a template calls ``t('some.key')`` for a key
that was never added to the catalogs, so the raw key string renders in the UI.
"""

import re
from pathlib import Path

from src.i18n.catalog_en import TEXTS as EN_TEXTS
from src.i18n.catalog_nl import TEXTS as NL_TEXTS

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "src" / "templates"

# Matches t('a.b.c') or t("a.b.c"), optionally followed by kwargs, but only when
# the key is a plain dotted string literal. Requiring at least one dot avoids
# matching JS calls that merely end in "t(", such as createElement('div').
# Dynamic keys like t('day.' ~ day) are intentionally skipped because they
# cannot be verified statically.
_T_CALL = re.compile(
    r"""t\(\s*['"]([a-z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)+)['"]\s*[),]"""
)


def _template_keys() -> dict[str, set[str]]:
    """Return a mapping of each translation key to the templates that use it."""
    keys: dict[str, set[str]] = {}
    for path in TEMPLATES_DIR.rglob("*.html"):
        for key in _T_CALL.findall(path.read_text(encoding="utf-8")):
            keys.setdefault(key, set()).add(path.name)
    return keys


def test_all_template_keys_exist_in_english_catalog() -> None:
    """Every statically-referenced template key must exist in the EN catalog.

    English is the runtime fallback catalog, so a key missing here surfaces as a
    raw ``some.key`` string to the user regardless of the active language.
    """
    missing = {
        key: sorted(templates)
        for key, templates in _template_keys().items()
        if key not in EN_TEXTS
    }
    assert not missing, f"Template keys missing from English catalog: {missing}"


def test_all_template_keys_exist_in_dutch_catalog() -> None:
    """Every statically-referenced template key must also exist in the NL catalog."""
    missing = {
        key: sorted(templates)
        for key, templates in _template_keys().items()
        if key not in NL_TEXTS
    }
    assert not missing, f"Template keys missing from Dutch catalog: {missing}"
