from pathlib import Path
from typing import cast

from litestar import Litestar, Request, get
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.logging import LoggingConfig
from litestar.openapi import OpenAPIConfig
from litestar.response import Template
from litestar.static_files import create_static_files_router
from litestar.template import TemplateConfig
from litestar.types.internal_types import TemplateConfigType
from tortoise import Tortoise

from src.controllers.elements import ElementController
from src.controllers.ingredients import IngredientController
from src.controllers.recipes import RecipeController
from src.controllers.tags import TagController
from src.db_config import TORTOISE_CONFIG
from src.models import User
from src.template_utils import render_markdown

DEBUG = True


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

    default_user_id: int | None = None
    user_count = await User.all().count()
    if user_count == 1:
        default_user = await User.get_default()
        default_user_id = default_user.id

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


async def init_db() -> None:
    await Tortoise.init(config=TORTOISE_CONFIG)
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
        await _ensure_recipe_owners(conn)
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
        RecipeController,
        IngredientController,
        TagController,
        ElementController,
        static_files_router,
    ],
    on_startup=[init_db],
    on_shutdown=[close_db],
    openapi_config=openapi_config,
    logging_config=logging_config,
    template_config=template_config,
    debug=DEBUG,
)
