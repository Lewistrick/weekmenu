from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "weeklygrocery" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "quantity" REAL NOT NULL,
    "ingredient_id" INT NOT NULL REFERENCES "ingredient" ("id") ON DELETE CASCADE,
    "owner_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "unit_id" INT NOT NULL REFERENCES "unit" ("id") ON DELETE CASCADE
) /* A recurring grocery a user buys every week, unrelated to the week menu. */;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "weeklygrocery";"""
