"""UI translation loading, lookup, and Jinja integration."""

from src.i18n.service import (
    DEFAULT_LANGUAGE_CODE,
    LANGUAGE_OPTIONS,
    LANGUAGE_OPTION_TO_CODE,
    clear_translation_cache,
    language_code_from_option,
    load_i18n_context,
    seed_english_texts,
    t,
)

__all__ = [
    "DEFAULT_LANGUAGE_CODE",
    "LANGUAGE_OPTIONS",
    "LANGUAGE_OPTION_TO_CODE",
    "clear_translation_cache",
    "language_code_from_option",
    "load_i18n_context",
    "seed_english_texts",
    "t",
]
