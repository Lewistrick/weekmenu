"""Litestar application entry point and global middleware."""

from pathlib import Path
from typing import cast

from litestar import Litestar, Request, get
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.logging import LoggingConfig
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar.openapi import OpenAPIConfig
from litestar.response import File, Redirect, Response, Template
from litestar.static_files import create_static_files_router
from litestar.template import TemplateConfig
from litestar.types.internal_types import TemplateConfigType

import src.db_config as db_config
from src.auth import SESSION_USER_KEY, get_current_user
from src.controllers.auth import AuthController
from src.controllers.elements import ElementController
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

DEBUG = True
SESSION_SECRET = b"weekmenu-session-secret-key-32b!"
session_config = CookieBackendConfig(secret=SESSION_SECRET)
FAVICON_PATH = Path("src/static/favicon.svg")
PUBLIC_PATH_PREFIXES = ("/login", "/register", "/static", "/schema", "/favicon.ico")


def _is_public_path(path: str) -> bool:
    """Return whether a path can be accessed without authentication."""
    return any(
        path == prefix or path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES
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

    if await get_current_user(request) is not None:
        return None

    request.session.pop(SESSION_USER_KEY, None)

    if request.headers.get("HX-Request"):
        return Response(content=b"", status_code=200, headers={"HX-Redirect": "/login"})

    return Redirect(path="/login")


def register_template_filters(template_engine: JinjaTemplateEngine) -> None:
    """Register custom Jinja filters and globals."""
    template_engine.engine.filters["markdown"] = render_markdown
    template_engine.engine.globals["t"] = t  # ty: ignore[invalid-assignment]


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
    """Load i18n context and enforce authentication."""
    await load_i18n_context(request)
    return await require_authentication(request)


async def init_db() -> None:
    """Initialize the database and apply aerich migrations on startup."""
    ensure_not_using_production_db_in_tests()
    await init_database(db_config.TORTOISE_CONFIG)
    await seed_english_texts()
    await seed_dutch_texts()


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

app = Litestar(
    route_handlers=[
        index,
        favicon,
        AuthController,
        RecipeController,
        IngredientController,
        IngredientUnitMergeController,
        TagController,
        UnitController,
        ShopController,
        WeekMenuController,
        WeeklyGroceryController,
        ElementController,
        static_files_router,
    ],
    middleware=[session_config.middleware],
    before_request=before_request,
    on_startup=[init_db],
    on_shutdown=[close_db],
    openapi_config=openapi_config,
    logging_config=logging_config,
    template_config=template_config,
    debug=DEBUG,
)
