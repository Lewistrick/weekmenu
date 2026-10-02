from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


# Adds the shelf icon and fills it once from the shelf name (snapshot of
# src/category_icons.icon_backfill_sql at the time of writing).
async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "ingredientcategory" ADD "icon" TEXT NOT NULL DEFAULT '';
        UPDATE "ingredientcategory" SET "icon" = CASE
            WHEN lower("name") LIKE '%groente%' THEN '🥦'
            WHEN lower("name") LIKE '%vegetable%' THEN '🥦'
            WHEN lower("name") LIKE '%fruit%' THEN '🍎'
            WHEN lower("name") LIKE '%vlees%' THEN '🥩'
            WHEN lower("name") LIKE '%meat%' THEN '🥩'
            WHEN lower("name") LIKE '%vis%' THEN '🐟'
            WHEN lower("name") LIKE '%fish%' THEN '🐟'
            WHEN lower("name") LIKE '%eiwit%' THEN '🫘'
            WHEN lower("name") LIKE '%protein%' THEN '🫘'
            WHEN lower("name") LIKE '%zuivel%' THEN '🧀'
            WHEN lower("name") LIKE '%dairy%' THEN '🧀'
            WHEN lower("name") LIKE '%kruid%' THEN '🌿'
            WHEN lower("name") LIKE '%specerij%' THEN '🌿'
            WHEN lower("name") LIKE '%herb%' THEN '🌿'
            WHEN lower("name") LIKE '%spice%' THEN '🌿'
            WHEN lower("name") LIKE '%brood%' THEN '🍞'
            WHEN lower("name") LIKE '%bread%' THEN '🍞'
            WHEN lower("name") LIKE '%bakery%' THEN '🍞'
            WHEN lower("name") LIKE '%vriez%' THEN '🧊'
            WHEN lower("name") LIKE '%vries%' THEN '🧊'
            WHEN lower("name") LIKE '%freez%' THEN '🧊'
            WHEN lower("name") LIKE '%frozen%' THEN '🧊'
            WHEN lower("name") LIKE '%sauz%' THEN '🫙'
            WHEN lower("name") LIKE '%saus%' THEN '🫙'
            WHEN lower("name") LIKE '%sauce%' THEN '🫙'
            WHEN lower("name") LIKE '%condiment%' THEN '🫙'
            WHEN lower("name") LIKE '%voorraad%' THEN '🥫'
            WHEN lower("name") LIKE '%pantry%' THEN '🥫'
            WHEN lower("name") LIKE '%drank%' THEN '🥤'
            WHEN lower("name") LIKE '%drink%' THEN '🥤'
            WHEN lower("name") LIKE '%overig%' THEN '📦'
            WHEN lower("name") LIKE '%other%' THEN '📦'
            ELSE '' END
        WHERE "icon" = '';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "ingredientcategory" DROP COLUMN "icon";"""


MODELS_STATE = (
    "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"
)
