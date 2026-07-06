from pathlib import Path

from litestar import Litestar, Request, get
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.logging import LoggingConfig
from litestar.openapi import OpenAPIConfig
from litestar.response import File, Template
from litestar.static_files import create_static_files_router
from litestar.template import TemplateConfig
from tortoise import Tortoise

from src.controllers.elements import ElementController
from src.controllers.ingredients import IngredientController
from src.controllers.recipes import RecipeController
from src.controllers.tags import TagController
from src.db_config import TORTOISE_CONFIG

DEBUG = True

FAVICON_PATH = Path("src/static/favicon.svg")


@get("/", tags=["home"])
async def index(request: Request) -> Template:
    return Template(template_name="index.html", context={"request": request})


@get("/favicon.ico", include_in_schema=False)
async def favicon() -> File:
    """Serve the site icon for browsers that request /favicon.ico by default."""
    return File(path=FAVICON_PATH, media_type="image/svg+xml")


async def init_db() -> None:
    await Tortoise.init(config=TORTOISE_CONFIG)
    await Tortoise.generate_schemas(safe=True)


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
template_config: TemplateConfig = TemplateConfig(
    engine=JinjaTemplateEngine, directory=Path("src/templates")
)

app = Litestar(
    route_handlers=[
        index,
        favicon,
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
