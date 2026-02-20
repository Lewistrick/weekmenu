from pathlib import Path

from litestar import Litestar, Request, get
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.logging import LoggingConfig
from litestar.openapi import OpenAPIConfig
from litestar.response import Template
from litestar.static_files import StaticFilesConfig
from litestar.template import TemplateConfig
from tortoise import Tortoise

from src.controllers.ingredients import IngredientController
from src.controllers.recipes import RecipeController
from src.controllers.tags import TagController
from src.db_config import TORTOISE_CONFIG

DEBUG = True


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
    template_config=TemplateConfig(
        directory=Path("src/templates"),
        engine=JinjaTemplateEngine,
    ),
    debug=DEBUG,
)
