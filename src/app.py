from litestar import Litestar, get
from litestar.logging import LoggingConfig
from litestar.openapi import OpenAPIConfig
from tortoise import Tortoise

from src.controllers.ingredients import IngredientController
from src.controllers.recipes import RecipeController
from src.db_config import TORTOISE_CONFIG

DEBUG = True


@get("/", tags=["home"])
async def index() -> str:
    return "Welkom bij weekmenu!"


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
    debug=DEBUG,
)
