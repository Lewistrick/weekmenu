# Weekmenu

Plan dinners for the week from your own recipes, then turn that plan into a grocery list sorted by shop.

## What you can do

- **Recipes** — Add, edit, search, and tag recipes. Optionally attach an image via an http(s) URL (`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, or `.avif` — not SVG). Mark recipes public so others can view or import them; keep yours private by default. Find recipes missing tags or a description and fill them in quickly.
- **Week menu** — Fill each day with a recipe (search, pin, or randomize). Set servings per day, reorder days, and optionally constrain random picks by tags (same tag all week, vary across the week, or at least N days with a tag). Copy the week as plain text when you want to share it.
- **Grocery list** — Generate from the week menu (replace, add to, or keep an existing list). Sort items into shops, mark things to check or already have, edit amounts, and copy a shop-grouped list for messaging. Add one-off items or your saved weekly staples in one click.
- **Your catalog** — Ingredients, units, tag groups, and shops are yours alone. Merge duplicate ingredients or units when things get messy. Manage recurring weekly groceries under Settings.

Open pages from the home screen tiles or the navbar (same destinations).

## Accounts

You need an account to use the app. Self-registration is closed: an **admin** creates users under **Admin → Users** and shows a one-time temporary password. The new person logs in, sets their own password, then can use the app.

In **Account** (Settings) you can change email, language, default servings, password, or delete your account.

Admins can also edit UI translations under **Admin → Translations**, and view deployment details under **Admin → Technical info** (database backend, PostgreSQL version, and runtime info).

## Run it locally

```bash
uv run litestar --app src.app:app run -r
```

Drop `-r` when you are not editing code. For other devices on your network:

```bash
uv run litestar --app src.app:app run -r --host 0.0.0.0 --port 8000
```

Local `uv run` defaults to SQLite at `src/recipes.sqlite3` unless `DATABASE_URL` is set. API docs: [http://127.0.0.1:8000/schema/swagger](http://127.0.0.1:8000/schema/swagger)

## Deploy with Docker

1. Copy `.env.example` to `.env` and set a strong `SESSION_SECRET` and `POSTGRES_PASSWORD`.
2. `docker compose up --build`
3. One-time data import from an existing SQLite file (after Postgres is healthy):
   `uv run python scripts/migrate_sqlite_to_postgres.py --sqlite data/recipes.sqlite3`

The site is served at `http://<host-IP>/weekmenu` on port **80** (HTTP only for now). Open firewall port 80; leave 8000 closed to the public.

Keep SQLite backups under `data/backups/` before migrating. Compose stores Postgres data in the `pg-data` volume.

## For developers

**Database** — Models live in `src/models.py`. Docker Compose runs **PostgreSQL**; set `DATABASE_URL` accordingly. Tests keep using in-memory SQLite. Local SQLite still uses aerich migrations (`uv run aerich migrate` / `upgrade`). Postgres schemas are created with Tortoise `generate_schemas` on startup. Diagram sketch: paste `dbdiagram.txt` into [dbdiagram.io](https://dbdiagram.io).

**Tests / lint** — `uv run pytest`, `uv run ruff format`, `uv run ruff check`. Optional: `uv run pre-commit install`.

**i18n** — UI strings seed from `src/i18n/catalog_en.py` and `catalog_nl.py`; icons from `src/i18n/icons.py`. Dutch catalog can be rebuilt with `uv run python scripts/build_catalog_nl.py`.
