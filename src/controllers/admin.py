"""Admin-only pages for users and UI translations."""

from litestar import Controller, Request, get, post
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template

from src.admin_translations import (
    language_choices,
    list_translation_tree,
    normalize_language_code,
    save_translation_texts,
)
from src.auth import require_admin


def _parse_groups(raw_values: list[str]) -> set[str] | None:
    """Parse top-level group checkbox values from query data."""
    values = [value.strip() for value in raw_values if value.strip()]
    return set(values) or None


def _parse_bool(raw: object) -> bool:
    """Return whether a checkbox-like value is enabled."""
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "on", "yes"}


def _query_group_values(request: Request) -> list[str]:
    """Collect all ``group`` query parameter values."""
    values: list[str] = []
    for key, value in request.query_params.multi_items():
        if key == "group":
            values.append(str(value))
    return values


class AdminController(Controller):
    """Admin section: users placeholder and translations editor."""

    path = "/admin"
    tags = ["admin"]

    @get("/users")
    async def users_page(self, request: Request) -> Template:
        """Render a placeholder users admin page."""
        await require_admin(request)
        return Template(
            template_name="admin-users.html",
            context={"request": request},
        )

    @get("/translations")
    async def translations_page(
        self,
        request: Request,
        language: str | None = None,
        search: str | None = None,
        incomplete_only: str | None = None,
    ) -> Template:
        """Render the translations management page."""
        await require_admin(request)
        language_code = normalize_language_code(language)
        groups = _parse_groups(_query_group_values(request))
        tops, tree = await list_translation_tree(
            language_code=language_code,
            groups=groups,
            search=search or "",
            incomplete_only=_parse_bool(incomplete_only),
        )
        selected_groups = groups or set()
        return Template(
            template_name="admin-translations.html",
            context={
                "request": request,
                "language_code": language_code,
                "language_choices": language_choices(),
                "top_level_groups": tops,
                "selected_groups": selected_groups,
                "search": search or "",
                "incomplete_only": _parse_bool(incomplete_only),
                "tree": tree,
            },
        )

    @get("/translations/list")
    async def translations_list(
        self,
        request: Request,
        language: str | None = None,
        search: str | None = None,
        incomplete_only: str | None = None,
    ) -> Template:
        """Return the filtered hierarchical translations list partial."""
        await require_admin(request)
        language_code = normalize_language_code(language)
        groups = _parse_groups(_query_group_values(request))
        _tops, tree = await list_translation_tree(
            language_code=language_code,
            groups=groups,
            search=search or "",
            incomplete_only=_parse_bool(incomplete_only),
        )
        return Template(
            template_name="partials/admin-translations-list.html",
            context={
                "request": request,
                "language_code": language_code,
                "tree": tree,
            },
        )

    @post("/translations/save")
    async def save_translation(
        self,
        request: Request,
        data: dict[str, str] = Body(media_type=RequestEncodingType.URL_ENCODED),
    ) -> Template:
        """Save English and selected-language text for one translation key."""
        await require_admin(request)
        key = str(data.get("key", "")).strip()
        language_code = normalize_language_code(data.get("language"))
        row = await save_translation_texts(
            key,
            english_text=str(data.get("english_text", "")),
            selected_language=language_code,
            selected_text=str(data.get("selected_text", "")),
        )
        return Template(
            template_name="partials/admin-translations-row.html",
            context={
                "request": request,
                "language_code": language_code,
                "row": row,
                "saved": True,
            },
        )
