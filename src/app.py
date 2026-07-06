from pathlib import Path
from typing import cast

from litestar import Litestar, Request, get
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.logging import LoggingConfig
from litestar.openapi import OpenAPIConfig
from litestar.response import Template
from litestar.static_files import StaticFilesConfig
from litestar.template import TemplateConfig
from litestar.types.internal_types import TemplateConfigType
from tortoise import Tortoise

from src.controllers.ingredients import IngredientController
from src.controllers.recipes import RecipeController
from src.controllers.tags import TagController
from src.db_config import TORTOISE_CONFIG
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


async def init_db() -> None:
    await Tortoise.init(config=TORTOISE_CONFIG)
    await Tortoise.generate_schemas(safe=True)


async def close_db() -> None:
    await Tortoise.close_connections()


app = Litestar(
    route_handlers=[
        index,
        RecipeController,
        IngredientController,
        TagController,
    ],
    on_startup=[init_db],
    on_shutdown=[close_db],
    openapi_config=OpenAPIConfig(
        title="Weekmenu API",
        version="1.0.0",
    ),
    logging_config=LoggingConfig(
        handlers={"default": {"class": "src.log_utils.InterceptHandler"}},
        formatters={"standard": {"format": "%(message)s"}},
    ),
    static_files_config=[
        StaticFilesConfig(path="/static", directories=["src/static"]),
    ],
    template_config=template_config,
    debug=DEBUG,
)
