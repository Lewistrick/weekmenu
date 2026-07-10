from pathlib import Path
from typing import cast

from litestar import Litestar, Request, get
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.logging import LoggingConfig
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar.openapi import OpenAPIConfig
from litestar.response import Redirect, Response, Template
from litestar.static_files import create_static_files_router
from litestar.template import TemplateConfig
from litestar.types.internal_types import TemplateConfigType

import src.db_config as db_config
from src.auth import SESSION_USER_KEY, get_current_user
from src.controllers.auth import AuthController
from src.controllers.elements import ElementController
from src.controllers.ingredients import IngredientController
from src.controllers.recipes import RecipeController
from src.controllers.shops import ShopController
from src.controllers.tags import TagController
from src.controllers.week_menu import WeekMenuController
from src.database import (
    close_database,
    ensure_not_using_production_db_in_tests,
    init_database,
)
from src.template_utils import render_markdown

DEBUG = True

SESSION_SECRET = b"weekmenu-session-secret-key-32b!"

session_config = CookieBackendConfig(secret=SESSION_SECRET)


PUBLIC_PATH_PREFIXES = ("/login", "/register", "/static", "/schema")


def _is_public_path(path: str) -> bool:
    """Return whether a path can be accessed without authentication."""

    return any(path == prefix or path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)


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
    """Register custom Jinja filters."""

    template_engine.engine.filters["markdown"] = render_markdown


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

    return Template(template_name="index.html", context={"request": request})


async def init_db() -> None:
    """Initialize the database and apply aerich migrations on startup."""

    ensure_not_using_production_db_in_tests()

    await init_database(db_config.TORTOISE_CONFIG)


async def close_db() -> None:

    await close_database()


openapi_config = OpenAPIConfig(title="Weekmenu", version="1.0.0")

logging_config = LoggingConfig(
    handlers={"default": {"class": "src.log_utils.InterceptHandler"}},
    formatters={"standard": {"format": "%(message)s"}},
)

static_files_router = create_static_files_router(path="/static", directories=["src/static"])


app = Litestar(
    route_handlers=[
        index,
        AuthController,
        RecipeController,
        IngredientController,
        TagController,
        ShopController,
        WeekMenuController,
        ElementController,
        static_files_router,
    ],
    middleware=[session_config.middleware],
    before_request=require_authentication,
    on_startup=[init_db],
    on_shutdown=[close_db],
    openapi_config=openapi_config,
    logging_config=logging_config,
    template_config=template_config,
    debug=DEBUG,
)
