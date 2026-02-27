from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "recipetag" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "recipe_id" INT NOT NULL REFERENCES "recipe" ("id") ON DELETE CASCADE,
    "tag_id" INT NOT NULL REFERENCES "tag" ("id") ON DELETE CASCADE
) /* A tag linked to a category. */;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "recipetag";"""


MODELS_STATE = (
    "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"
)
