from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "shop" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL
);
        CREATE TABLE IF NOT EXISTS "user" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "username" TEXT NOT NULL,
    "email" TEXT NOT NULL
);
        CREATE TABLE IF NOT EXISTS "useringredientshop" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "ingredient_id" INT NOT NULL REFERENCES "ingredient" ("id") ON DELETE CASCADE,
    "shop_id" INT REFERENCES "shop" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "shop";
        DROP TABLE IF EXISTS "useringredientshop";
        DROP TABLE IF EXISTS "user";"""


MODELS_STATE = (
    "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"
    "iXoQ=="
)
