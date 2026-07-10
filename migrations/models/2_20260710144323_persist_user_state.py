"""Persist week menus, grocery lists, and user preferences in the database."""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    """Create tables for persisted user state."""
    return """
        CREATE TABLE IF NOT EXISTS "grocerylistitem" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "quantity" REAL NOT NULL,
    "status" TEXT NOT NULL,
    "ingredient_id" INT NOT NULL REFERENCES "ingredient" ("id") ON DELETE CASCADE,
    "shop_id" INT REFERENCES "shop" ("id") ON DELETE SET NULL,
    "unit_id" INT NOT NULL REFERENCES "unit" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_grocerylist_user_id_3198a9" UNIQUE ("user_id", "ingredient_id", "unit_id")
) /* One line on a user's active grocery list. */;
        CREATE TABLE IF NOT EXISTS "userpreference" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "language" TEXT NOT NULL,
    "default_servings" INT NOT NULL DEFAULT 2,
    "start_day" TEXT NOT NULL,
    "include_public" INT NOT NULL DEFAULT 0,
    "grocery_list_initialized" INT NOT NULL DEFAULT 0,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
) /* Per-user account and week-menu preferences persisted in the database. */;
        CREATE TABLE IF NOT EXISTS "weekmenuslot" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "day" TEXT NOT NULL,
    "pinned" INT NOT NULL DEFAULT 0,
    "servings" INT NOT NULL DEFAULT 2,
    "recipe_id" INT REFERENCES "recipe" ("id") ON DELETE SET NULL,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_weekmenuslo_user_id_842f01" UNIQUE ("user_id", "day")
) /* One day in a user's week menu. */;
        CREATE TABLE IF NOT EXISTS "weekmenutagconstraint" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "mode" TEXT NOT NULL,
    "minimum_count" INT NOT NULL DEFAULT 1,
    "category_id" INT NOT NULL REFERENCES "tagcategory" ("id") ON DELETE CASCADE,
    "tag_id" INT REFERENCES "tag" ("id") ON DELETE SET NULL,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_weekmenutag_user_id_f81eca" UNIQUE ("user_id", "category_id")
) /* Tag-group constraint for week menu randomization. */;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    """Drop persisted user-state tables."""
    return """
        DROP TABLE IF EXISTS "userpreference";
        DROP TABLE IF EXISTS "weekmenuslot";
        DROP TABLE IF EXISTS "grocerylistitem";
        DROP TABLE IF EXISTS "weekmenutagconstraint";"""


MODELS_STATE = (
    "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"
    "5+/B+Ip96R"
)
