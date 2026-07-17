"""Add color fields to tag categories for colored tag-group UI."""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    """Add tag category colors and backfill existing rows."""
    return """
        ALTER TABLE "tagcategory" ADD COLUMN "foreground_color" TEXT NOT NULL DEFAULT '#ffffff';
        ALTER TABLE "tagcategory" ADD COLUMN "background_color" TEXT NOT NULL DEFAULT '#2563eb';

        UPDATE "tagcategory"
        SET "background_color" = CASE ("id" % 6)
            WHEN 0 THEN '#2563eb'
            WHEN 1 THEN '#16a34a'
            WHEN 2 THEN '#f97316'
            WHEN 3 THEN '#e11d48'
            WHEN 4 THEN '#7c3aed'
            ELSE '#0ea5e9'
        END,
        "foreground_color" = CASE ("id" % 6)
            WHEN 2 THEN '#1b1b1b'
            ELSE '#ffffff'
        END;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    """SQLite cannot reliably drop columns via simple ALTER TABLE statements."""
    return ""


MODELS_STATE = (
    "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"
    "rxeV+xZA3oG7e7HkWs9iSoHLL8OiPcDnJ0+4AAiaKboM68WlBe9x/4O5VNW579k1qEmtWi"
    "dV3c9PzCyFm5TWnt8TJTWb59h/fc/p6D2mwxyvphZGFHM8OHPsTmy61sJI+6fSdTeoX34o"
    "3c3oFl3dTSaH5t3ZbKMKAl5IS1rPxGHr16zKWkrOP+UEdlV0UKIpUj5WRBu5mOrMNv8UCU"
    "NFlr5VC5XEfbVFnGLve2bvds3NqWL5FoOirFcbnNomNe3Anoklrhp9sqDXHiN4dejuqQ6m"
    "6OXxvoqyH003U5S9Ycqujj9p4PiTNk+U7q7HU3KgdBfcnaR8oMTNydQXVLs31tJIiW6wPy"
    "H3BANXbJwbn/8criGgebD0EHmCK9DwEAXUhWoIosMJdpBuVLEk0VC7cPRdCABalWsg/tXF"
    "bT0S4vDfIRGKUWyFR1ezBeKd2bG46Atx4PW3AFPf9Jf3FHKpoMbuJf8c7CMNUzQnCOt6+O"
    "GYLrOnYJsUMcoFtCqHTDlf+3W+4q9PYsQshkvwSyvlUFyAVqfnABlOH6Z3F5MR+nw9uhzf"
    "jKdXGccrvJkN81+PzieFPBRVCaEOtTuAA8FNbk0HItE4JtAqHAi1w2HM5NbvcKjKIZovh5"
    "Dve1i/+/Vue4I8dinT1KV8pXNOjrWHgcSDiO5Uug44kVnnM5QDqrhx69z4CUpAwvL0LHiX"
    "D9iVo5dS6Ut6Ee/132cWoYYPHfzs7dsKzOLFCS71MrcOEd06C+9lKQoMjRogRuL9BPDVzz"
    "9vACCXKgVQ3MutSTDqSyfZ/9xMr0oWJBKVHJB8lmD0i25q/lA44l+7CWsFivDW1atm+QUy"
    "QIF5Pp+YvbiBgx+W8eP/qz1OgQ=="
)
