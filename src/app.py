import os
from pathlib import Path
from typing import cast

from litestar import Litestar, Request, get
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.logging import LoggingConfig
from litestar.openapi import OpenAPIConfig
from litestar.response import Redirect, Response, Template
from litestar.static_files import create_static_files_router
from litestar.template import TemplateConfig
from litestar.types.internal_types import TemplateConfigType
from tortoise import Tortoise

from src.auth import SESSION_USER_KEY
from src.controllers.auth import AuthController
from src.controllers.elements import ElementController
from src.controllers.ingredients import IngredientController
from src.controllers.recipes import RecipeController
from src.controllers.tags import TagController
from src.controllers.week_menu import WeekMenuController
import src.db_config as db_config
from src.models import User
from src.template_utils import render_markdown

DEBUG = True
SESSION_SECRET = b"weekmenu-session-secret-key-32b!"
session_config = CookieBackendConfig(secret=SESSION_SECRET)

PUBLIC_PATH_PREFIXES = ("/login", "/register", "/static", "/schema")


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
    if request.session.get(SESSION_USER_KEY) is not None:
        return None
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


async def _ensure_recipe_owners(conn) -> None:
    """Add recipe.owner_id when missing and backfill null values."""
    table_info = await conn.execute_query("PRAGMA table_info(recipe)")
    columns = {row[1] for row in table_info[1]}

    first_user = await User.all().order_by("id").first()
    default_user_id = first_user.id if first_user else None

    if "owner_id" not in columns:
        if default_user_id is not None:
            await conn.execute_query(
                f"ALTER TABLE recipe ADD COLUMN owner_id INT NOT NULL DEFAULT {default_user_id}"
            )
        else:
            await conn.execute_query("ALTER TABLE recipe ADD COLUMN owner_id INT")

    if default_user_id is not None:
        await conn.execute_query(
            f"UPDATE recipe SET owner_id = {default_user_id} WHERE owner_id IS NULL"
        )


async def _ensure_user_auth_columns(conn) -> None:
    """Add the user.password_hash column when migrating an older database."""
    table_info = await conn.execute_query("PRAGMA table_info(user)")
    columns = {row[1] for row in table_info[1]}
    if "password_hash" not in columns:
        await conn.execute_query("ALTER TABLE user ADD COLUMN password_hash TEXT")


async def _ensure_recipe_attribution(conn) -> None:
    """Add recipe.creator_id and recipe.imported_from_id for older databases.

    Backfills ``creator_id`` from ``owner_id`` so existing recipes are credited
    to their owner.
    """
    table_info = await conn.execute_query("PRAGMA table_info(recipe)")
    columns = {row[1] for row in table_info[1]}
    if "creator_id" not in columns:
        await conn.execute_query("ALTER TABLE recipe ADD COLUMN creator_id INT")
    if "imported_from_id" not in columns:
        await conn.execute_query("ALTER TABLE recipe ADD COLUMN imported_from_id INT")
    await conn.execute_query(
        "UPDATE recipe SET creator_id = owner_id WHERE creator_id IS NULL"
    )


async def _ensure_not_using_production_db_in_tests() -> None:
    """Block accidental production database use while pytest is running."""
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return

    db_url = str(db_config.TORTOISE_CONFIG["connections"]["default"])
    if "recipes.sqlite3" in db_url:
        msg = "Tests must use the in-memory database, not src/recipes.sqlite3."
        raise RuntimeError(msg)


async def init_db() -> None:
    await _ensure_not_using_production_db_in_tests()
    await Tortoise.init(config=db_config.TORTOISE_CONFIG)
    await Tortoise.generate_schemas(safe=True)

    conn = Tortoise.get_connection("default")
    try:
        table_info = await conn.execute_query("PRAGMA table_info(recipe)")
        columns = {row[1] for row in table_info[1]}
        if "private" not in columns:
            await conn.execute_query(
                "ALTER TABLE recipe ADD COLUMN private BOOLEAN NOT NULL DEFAULT 1"
            )
        if "enabled" not in columns:
            await conn.execute_query(
                "ALTER TABLE recipe ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT 1"
            )
        await _ensure_user_auth_columns(conn)
        await _ensure_recipe_owners(conn)
        await _ensure_recipe_attribution(conn)
    except Exception:
        pass


async def close_db() -> None:
    await Tortoise.close_connections()


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
        AuthController,
        RecipeController,
        IngredientController,
        TagController,
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
