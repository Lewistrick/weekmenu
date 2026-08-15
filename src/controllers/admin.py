"""Admin-only pages for users and UI translations."""

from litestar import Controller, Request, get, post
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template

from src.admin_info import collect_admin_info
from src.admin_translations import (
    language_choices,
    list_translation_tree,
    normalize_language_code,
    save_translation_texts,
)
from src.auth import require_admin
from src.i18n.service import t
from src.invite_users import create_invited_user
from src.models import User


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
    """Admin section: invite users and translations editor."""

    path = "/admin"
    tags = ["admin"]

    @staticmethod
    async def _render_users_page(
        request: Request,
        *,
        messages: list[str] | None = None,
        warnings: list[str] | None = None,
        created_username: str | None = None,
        temporary_password: str | None = None,
        form_username: str = "",
        form_email: str = "",
    ) -> Template:
        """Render the users admin page with optional feedback."""
        users = await User.all().order_by("username")
        return Template(
            template_name="admin-users.html",
            context={
                "request": request,
                "users": users,
                "messages": messages or [],
                "warnings": warnings or [],
                "created_username": created_username,
                "temporary_password": temporary_password,
                "form_username": form_username,
                "form_email": form_email,
            },
        )

    @get("/users")
    async def users_page(self, request: Request) -> Template:
        """Render the users admin page with create form and user list."""
        await require_admin(request)
        return await self._render_users_page(request)

    @get("/info")
    async def info_page(self, request: Request) -> Template:
        """Render technical runtime information for administrators."""
        await require_admin(request)
        return Template(
            template_name="admin-info.html",
            context={
                "request": request,
                "info": await collect_admin_info(),
            },
        )

    @post("/users")
    async def create_user(
        self,
        request: Request,
        data: dict[str, str] = Body(media_type=RequestEncodingType.URL_ENCODED),
    ) -> Template:
        """Create an invited user with a one-time temporary password."""
        await require_admin(request)
        username = str(data.get("username", "")).strip()
        email = str(data.get("email", "")).strip()

        warnings: list[str] = []
        if not username:
            warnings.append(t("message.auth.username_required"))
        elif await User.get_by_username(username) is not None:
            warnings.append(t("message.auth.username_taken"))

        if warnings:
            return await self._render_users_page(
                request,
                warnings=warnings,
                form_username=username,
                form_email=email,
            )

        _user, temporary_password = await create_invited_user(
            username=username, email=email
        )
        return await self._render_users_page(
            request,
            messages=[t("admin.users.created", username=username)],
            created_username=username,
            temporary_password=temporary_password,
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
