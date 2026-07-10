from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "user" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "username" TEXT NOT NULL,
    "email" TEXT,
    "password_hash" TEXT
) /* An application user who owns recipes and shopping preferences. */;
CREATE TABLE IF NOT EXISTS "ingredient" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL,
    "owner_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
) /* Any ingredient (to add quantity and unit, see RecipeIngredient). */;
CREATE TABLE IF NOT EXISTS "recipe" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "prep_time_minutes" INT NOT NULL,
    "cook_time_minutes" INT NOT NULL,
    "servings" INT NOT NULL,
    "private" INT NOT NULL DEFAULT 1,
    "enabled" INT NOT NULL DEFAULT 1,
    "creator_id" INT REFERENCES "user" ("id") ON DELETE SET NULL,
    "imported_from_id" INT REFERENCES "recipe" ("id") ON DELETE SET NULL,
    "owner_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
) /* A recipe for your cookbook. */;
CREATE TABLE IF NOT EXISTS "shop" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL,
    "foreground_color" TEXT NOT NULL,
    "background_color" TEXT NOT NULL,
    "owner_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "tagcategory" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL,
    "owner_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
) /* A category of tags. */;
CREATE TABLE IF NOT EXISTS "tag" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL,
    "category_id" INT NOT NULL REFERENCES "tagcategory" ("id") ON DELETE CASCADE,
    "owner_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
) /* A tag belonging to a recipe. */;
CREATE TABLE IF NOT EXISTS "recipetag" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "recipe_id" INT NOT NULL REFERENCES "recipe" ("id") ON DELETE CASCADE,
    "tag_id" INT NOT NULL REFERENCES "tag" ("id") ON DELETE CASCADE
) /* A tag linked to a category. */;
CREATE TABLE IF NOT EXISTS "unit" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "abbrev" TEXT NOT NULL,
    "single" TEXT,
    "plural" TEXT,
    "owner_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
) /* A unit of measurement for an ingredient in a recipe, e.g. pieces, grams, liters. */;
CREATE TABLE IF NOT EXISTS "recipeingredient" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "quantity" REAL NOT NULL,
    "ingredient_id" INT NOT NULL REFERENCES "ingredient" ("id") ON DELETE CASCADE,
    "recipe_id" INT NOT NULL REFERENCES "recipe" ("id") ON DELETE CASCADE,
    "unit_id" INT NOT NULL REFERENCES "unit" ("id") ON DELETE CASCADE
) /* An ingredient in a recipe listing, including quantity and unit. */;
CREATE TABLE IF NOT EXISTS "useringredientshop" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "ingredient_id" INT NOT NULL REFERENCES "ingredient" ("id") ON DELETE CASCADE,
    "shop_id" INT REFERENCES "shop" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSON NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "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"
)
