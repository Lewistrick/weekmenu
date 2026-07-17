"""Add is_admin flag on users and grant admin to Erick."""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    """Add is_admin column and mark Erick as admin when present."""
    return """
        ALTER TABLE "user" ADD "is_admin" INT NOT NULL DEFAULT 0;
        UPDATE "user" SET "is_admin" = 1 WHERE "username" = 'Erick';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    """SQLite cannot reliably drop columns via simple ALTER TABLE statements."""
    return ""


MODELS_STATE = (
    "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"
)
