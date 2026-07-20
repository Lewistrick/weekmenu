"""Litestar application entry point and global middleware."""

import os
from pathlib import Path
from typing import cast

from litestar import Litestar, Request, Router, get
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.logging import LoggingConfig
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar.openapi import OpenAPIConfig
from litestar.response import File, Redirect, Response, Template
from litestar.static_files import create_static_files_router
from litestar.template import TemplateConfig
from litestar.types.internal_types import TemplateConfigType

import src.db_config as db_config
from src.auth import (
    SESSION_USER_KEY,
    ensure_default_admin,
    get_current_user,
    load_request_user,
    template_current_user,
)
from src.controllers.admin import AdminController
from src.controllers.auth import AuthController
from src.controllers.elements import ElementController
from src.controllers.ingredient_merge import IngredientMergeController
from src.controllers.ingredient_units import IngredientUnitMergeController
from src.controllers.ingredients import IngredientController
from src.controllers.recipes import RecipeController
from src.controllers.shops import ShopController
from src.controllers.tags import TagController
from src.controllers.units import UnitController
from src.controllers.week_menu import WeekMenuController
from src.controllers.weekly_groceries import WeeklyGroceryController
from src.database import (
    close_database,
    ensure_not_using_production_db_in_tests,
    init_database,
)
from src.i18n.service import load_i18n_context, seed_dutch_texts, seed_english_texts, t
from src.template_utils import render_markdown
from src.url_path import BasePathProxy, base_path, path_with_base, strip_base_path

DEBUG = os.environ.get("DEBUG", "true").lower() in ("1", "true", "yes")
SESSION_SECRET = os.environ.get(
    "SESSION_SECRET",
    "weekmenu-session-secret-key-32b!",
).encode()
session_config = CookieBackendConfig(secret=SESSION_SECRET)
FAVICON_PATH = Path("src/static/favicon.svg")
PUBLIC_PATH_PREFIXES = ("/login", "/register", "/static", "/schema", "/favicon.ico")
PASSWORD_CHANGE_ALLOWLIST = (
    "/login",
    "/logout",
    "/profile/password",
    "/static",
    "/favicon.ico",
)


def _is_public_path(path: str) -> bool:
    """Return whether a path can be accessed without authentication."""
    app_path = strip_base_path(path)
    return any(
        app_path == prefix or app_path.startswith(prefix)
        for prefix in PUBLIC_PATH_PREFIXES
    )


def _is_password_change_allowed(path: str) -> bool:
    """Return whether a must-change-password user may access this path."""
    app_path = strip_base_path(path)
    return any(
        app_path == prefix or app_path.startswith(prefix)
        for prefix in PASSWORD_CHANGE_ALLOWLIST
    )


async def require_authentication(request: Request) -> Response | None:
    """Redirect unauthenticated visitors to the login page.

    Args:
        request: The incoming request.

    Returns:
        A redirect response when authentication is required and missing,
        otherwise ``None`` to continue normal handling.
    """
    if _is_public_path(request.url.path):
        return None

    user = await get_current_user(request)
    if user is None:
        request.session.pop(SESSION_USER_KEY, None)
        login_path = path_with_base("/login")
        if request.headers.get("HX-Request"):
            return Response(
                content=b"", status_code=200, headers={"HX-Redirect": login_path}
            )
        return Redirect(path=login_path)

    if user.must_change_password and not _is_password_change_allowed(request.url.path):
        change_path = path_with_base("/profile/password")
        if request.headers.get("HX-Request"):
            return Response(
                content=b"", status_code=200, headers={"HX-Redirect": change_path}
            )
        return Redirect(path=change_path)

    return None


def register_template_filters(template_engine: JinjaTemplateEngine) -> None:
    """Register custom Jinja filters and globals."""
    template_engine.engine.filters["markdown"] = render_markdown
    template_engine.engine.globals["t"] = t  # ty: ignore[invalid-assignment]
    template_engine.engine.globals["current_user"] = (  # ty: ignore[invalid-assignment]
        template_current_user
    )
    template_engine.engine.globals["base_path"] = (  # ty: ignore[invalid-assignment]
        BasePathProxy()
    )
    template_engine.engine.globals["url"] = (  # ty: ignore[invalid-assignment]
        path_with_base
    )


def create_template_engine() -> JinjaTemplateEngine:
    """Create and configure the Jinja template engine."""
    template_engine = JinjaTemplateEngine(directory=Path("src/templates"))

    register_template_filters(template_engine)

    return template_engine


template_config = cast(
    TemplateConfigType,
    TemplateConfig(instance=create_template_engine()),
)


@get("/", tags=["home"])
async def index(request: Request) -> Template:
    """Render the home page."""
    return Template(template_name="index.html", context={"request": request})


@get("/favicon.ico", include_in_schema=False)
async def favicon() -> File:
    """Serve the site icon for browsers that request /favicon.ico by default."""
    return File(path=FAVICON_PATH, media_type="image/svg+xml")


async def before_request(request: Request) -> Response | None:
    """Load request user, i18n context, and enforce authentication."""
    await load_request_user(request)
    await load_i18n_context(request)
    return await require_authentication(request)


async def init_db() -> None:
    """Initialize the database and apply aerich migrations on startup."""
    ensure_not_using_production_db_in_tests()
    await init_database(db_config.TORTOISE_CONFIG)
    await seed_english_texts()
    await seed_dutch_texts()
    await ensure_default_admin()


async def close_db() -> None:
    """Close database connections on application shutdown."""
    await close_database()


openapi_config = OpenAPIConfig(title="Weekmenu", version="1.0.0")
logging_config = LoggingConfig(
    handlers={"default": {"class": "src.log_utils.InterceptHandler"}},
    formatters={"standard": {"format": "%(message)s"}},
)
static_files_router = create_static_files_router(
    path="/static", directories=["src/static"]
)

_app_route_handlers: list = [
    index,
    favicon,
    AuthController,
    RecipeController,
    IngredientController,
    IngredientUnitMergeController,
    IngredientMergeController,
    TagController,
    UnitController,
    ShopController,
    WeekMenuController,
    WeeklyGroceryController,
    AdminController,
    ElementController,
    static_files_router,
]

_configured_base = base_path()
if _configured_base:
    _route_handlers: list = [
        Router(path=_configured_base, route_handlers=_app_route_handlers)
    ]
else:
    _route_handlers = _app_route_handlers

app = Litestar(
    route_handlers=_route_handlers,
    middleware=[session_config.middleware],
    before_request=before_request,
    on_startup=[init_db],
    on_shutdown=[close_db],
    openapi_config=openapi_config,
    logging_config=logging_config,
    template_config=template_config,
    debug=DEBUG,
)
