"""Application URL path helpers for optional deploy base path prefix."""

import os


def base_path() -> str:
    """Return the configured URL base path (no trailing slash), or empty.

    Set ``APP_BASE_PATH`` to something like ``/weekmenu`` when the app is served
    under a subdirectory. Local development and tests leave it unset.
    """
    raw = os.environ.get("APP_BASE_PATH", "").strip()
    if not raw or raw == "/":
        return ""
    if not raw.startswith("/"):
        raw = f"/{raw}"
    return raw.rstrip("/")


class BasePathProxy:
    """Jinja-friendly proxy that always reads the current ``APP_BASE_PATH``."""

    def __str__(self) -> str:
        """Return the live base path string."""
        return base_path()

    def __html__(self) -> str:
        """Return the live base path for HTML rendering."""
        return base_path()


def path_with_base(path: str) -> str:
    """Prefix an absolute app path with the configured base path.

    Args:
        path: An application path beginning with ``/``, or empty for home.

    Returns:
        The path including ``APP_BASE_PATH`` when configured.
    """
    if not path.startswith("/"):
        path = f"/{path}"
    base = base_path()
    if not base:
        return path if path != "/" else "/"
    if path == "/":
        return f"{base}/"
    return f"{base}{path}"


def strip_base_path(path: str) -> str:
    """Remove the configured base path prefix from a request path.

    Args:
        path: The raw request URL path.

    Returns:
        The path as seen by route handlers when no base is set, or the
        remainder after stripping ``APP_BASE_PATH``.
    """
    base = base_path()
    if not base:
        return path
    if path == base:
        return "/"
    if path.startswith(f"{base}/"):
        return path[len(base) :] or "/"
    return path
