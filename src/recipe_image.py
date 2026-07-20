"""Validation helpers for recipe image URLs."""

from urllib.parse import urlparse

from src.i18n.service import t

ALLOWED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif")
MAX_IMAGE_URL_LENGTH = 2048


def parse_recipe_image_url(raw: object) -> tuple[bool, str | None, str | None]:
    """Validate an optional http(s) image URL for a recipe.

    Empty input clears the image (``None``). Only ``http``/``https`` URLs whose
    path ends with a non-SVG image extension are accepted. Query strings are
    allowed so CDN URLs still work.

    Args:
        raw: Form value (typically a string).

    Returns:
        ``(ok, normalized_url_or_none, error_message_or_none)``.
    """
    if raw is None:
        return True, None, None

    value = str(raw)
    if any(ord(char) < 32 for char in value):
        return False, None, t("message.recipe.image_url_invalid")

    value = value.strip()
    if not value:
        return True, None, None

    if len(value) > MAX_IMAGE_URL_LENGTH:
        return False, None, t("message.recipe.image_url_too_long")

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return False, None, t("message.recipe.image_url_scheme")

    if not parsed.netloc:
        return False, None, t("message.recipe.image_url_invalid")

    if parsed.username is not None or parsed.password is not None:
        return False, None, t("message.recipe.image_url_credentials")

    path = parsed.path.lower()
    if not any(path.endswith(ext) for ext in ALLOWED_IMAGE_EXTENSIONS):
        return False, None, t("message.recipe.image_url_extension")

    return True, value, None
