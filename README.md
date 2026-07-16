# Weekmenu

## Usage
### To start the app
- `uv run litestar --app src.app:app run -r`
    - (remove `-r` when not editing the code)
- To open the app on other devices on your home network, bind to all interfaces:
  `uv run litestar --app src.app:app run -r --host 0.0.0.0 --port 8000`

### Docker (local)
- Copy `.env.example` to `.env` and set a strong `SESSION_SECRET`.
- Start the app: `docker compose up --build`
- Open [http://localhost:8000](http://localhost:8000) (or the port set in `APP_PORT`).
- The SQLite database is stored in a Docker volume (`sqlite-data`) mounted at `src/recipes.sqlite3`.
- Aerich migrations run automatically when the app container starts.
- PostgreSQL is included but disabled by default. To start it alongside the app (for future use):
  `docker compose --profile postgres up --build`
  The app still uses SQLite until `DATABASE_URL` is wired in `src/db_config.py`.

### Accounts and login
- The app requires an account. Visiting any page while logged out redirects to the login page.
- Create an account at `/register` with a username, a password (min. 6 characters), and an optional email address. Registering logs you in automatically.
- Log in at `/login` and log out from the "🚪 Log out" item in the ⚙️ Settings menu.
- Manage your account at `/profile` (reachable via ⚙️ Settings → 👤 Account): update your email, language, default week-menu servings, change your password, or delete your account (which removes the account and its recipes).
- Passwords are hashed with bcrypt and the logged-in user is tracked in a signed cookie session.

### Recipe sharing and privacy
- Every recipe has an **owner** (who controls it), a **creator** (who originally wrote it), and a private/public flag (toggle on the edit page). New recipes start private with you as both owner and creator.
- You always see and manage your own recipes. You can also open other users' **public** recipes (read-only) via direct links or search when you opt in.
- By default, recipe search, the random **private** recipe picker, listings, and week-menu tools only use **your own** recipes. Check **Include public recipes** on the search or week menu page to also show other users' public recipes in those tools.
- Use **Random public recipe** to jump straight to a random public recipe owned by another user.
- Import a public recipe you do not own with **Import to my recipes** on its view page. This creates a private copy in your collection, keeps the original creator credited, and blocks importing the same public recipe twice.
- Trying to edit or delete a recipe you do not own returns a 404.

### Per-user week menu
- Your week menu, start day, tag constraints, include-public preference, and grocery list are stored in the database per account, so they follow you across browsers and devices when you log in.
- Week menu randomization and per-day recipe search use your own recipes by default; enable **Include public recipes** in the week menu toolbar to widen the pool.
- New empty week-menu slots use your profile setting for default servings.

### Account settings
- Language and default week-menu servings are stored in the database per account.
- Legacy `user_settings/{user_id}.json` files are imported automatically the first time settings are loaded after upgrading.
- Settings are editable from `/profile` under the **Settings** section.

### Internationalization (i18n)
- User-facing UI strings are stored in the `uitext` database table (`language_code`, `key`, `text`) and loaded per request based on the account language setting.
- English strings are seeded from `src/i18n/catalog_en.py` on startup and in tests.
- Dutch strings are seeded from `src/i18n/catalog_nl.py` (regenerate from `translations.xlsx` with `uv run python scripts/build_catalog_nl.py`).
- Language-independent icons (nav emojis, action buttons, etc.) live in `src/i18n/icons.py` and are added by `t()` at render time, not stored in the database.
- Templates use the Jinja global `t('key')`; controllers use `t()` from `src/i18n.service` for flash messages and errors.
- When a translation is missing for the selected language, the app falls back to English, then to the key itself.

### Grocery lists by shop and plaintext export
- Open the grocery list from the navbar or home page (`/week-menu/grocery-list`). Use **Generate grocery list** on the week menu page to create or update the list from your current week menu.
- At the top of the grocery list page you can **add your own groceries** that are unrelated to the week menu: enter an ingredient name, an amount, and pick a unit, then click **Add**. Adding an item that matches an existing line (same ingredient and unit) sums the amounts. If no list exists yet, adding an item starts one.
- The top of the grocery list page also has an **🧺 Add weekly groceries** button that appends every saved weekly grocery to the current list in one click (see below). Adding and weekly-grocery buttons update the list in place via HTMX without reloading the page.
- Manage shops at `/shops/manage` (⚙️ Settings → 🏪 Shops). Each shop has a name plus foreground and background colors used on the grocery list.
- Generating from the week menu creates a new list when empty, or lets you **Replace** the current list, **Add** week-menu groceries to it, or cancel. Visiting the grocery list page directly preserves a non-empty list and shows a notice instead of regenerating over your sorting work.
- The grocery list uses a two-column layout: **To sort** (unassigned items with one-click shop buttons, a **?** chip for items to verify later, and a ✓ **already have** chip) on the left, and solid-color shop lists on the right. Items marked **To check** or **Already have** appear in subsections below the unsorted list and can be moved back with the same chips.
- Moving an ingredient to a shop, to-check, or already-have updates the list in place (no full page reload), so your scroll position is preserved.
- When the same ingredient appears in more than one unit (e.g. grams and kilograms), shop and status buttons affect only that specific line.
- Shop selection uses colored chip buttons showing the first letter of the shop name. Amounts are shown on the right and can be edited with a click.
- Copy grouped plaintext for messaging under the grocery columns (ingredients by shop).
- Amounts are shown on the right and can be edited with a click. Lines are identified by ingredient and unit, so duplicate units merge when you edit.
- Each shop section has a **Mark all ✓** button. The to-check and already-have lists each have a **🗑 Clear list** button (amber warning style) with inline confirmation; clearing either list removes those groceries from the plan entirely.
- Export the week menu as plaintext via `GET /week-menu/export` (`{day} - {recipe}` per line, empty days omitted).

### Weekly groceries
- Keep a personal list of recurring groceries (staples you buy every week) that is unrelated to the week menu. Manage it at `/weekly-groceries/manage` (⚙️ Settings → 🧺 Weekly groceries).
- Each weekly grocery has an ingredient name, an amount, and a unit. Names reuse your ingredient catalog (so shop assignments still apply), units must be existing units, and duplicates (same ingredient and unit) are rejected.
- Weekly groceries are saved in the database per user, so they persist across sessions.
- Add them all to your grocery list with the **🧺 Add weekly groceries** button at the top of the grocery list page; only groceries not already on the list are added, and matching lines are merged when they are added.

### Per-user catalog (ingredients, units, tags, shops)
- Ingredients, units, tag groups, tag values, and shops belong to an account. You only see and manage your own catalog data in lists, forms, and API responses.
- Registering a new account seeds a default unit set: `g`, `kg`, `ml`, `l`, `el`, `tl`, `st` (with singular/plural labels where applicable).
- Manage units at `/units/manage` (⚙️ Settings → 📏 Units): edit abbreviation, singular, and plural labels, add new units, or delete unused ones. Units missing a singular or plural label show a warning.
- Merge ingredient units at `/ingredients/merge-units/manage` (⚙️ Settings → 🔀 Merge ingredient units): find ingredients that appear with more than one unit, then convert all uses to a single unit by entering a ratio on both sides (for example, `200 gram = 1 piece`).
- Merge ingredients at `/ingredients/merge/manage` (⚙️ Settings → 🔗 Merge ingredients): combine duplicate ingredients such as oil and olive oil. Pick which name to keep; recipe lines with the same unit are summed, and the other ingredient is removed.
- Multiple units may share the same abbreviation when their singular or plural labels differ.
- When you import a public recipe, its ingredients, units, and tags are remapped into your catalog (matched by name where possible) so edits stay isolated from the original author's data.

### What will it be able to do
- Compose your own cookbook
- Organize recipes with tag groups and values (for example: season, carb type, diet)
- Create a random week menu, giving you a random recipe for each day of the week
    - Optional tag constraints when randomizing: same tag for every day, vary tags across the week, or at least N days with a chosen tag
    - Reorder meals by moving a day's recipe up or down the week
    - Enter the number of servings for each day; amounts are scaled from each recipe's own serving count
- Generate a grocery list from the week menu
    - Ingredient quantities are scaled to each day's servings, then ingredients sharing the same name and unit are added together
- Generate a grocery list from the week menu via **Generate grocery list** at the bottom of the week menu page
- Add your own one-off groceries to the grocery list, unrelated to the week menu
- Keep a reusable list of weekly groceries and add them all to the grocery list in one click
- Search recipes by name, description, ingredients, and optional tag filters

### To see the API docs
- [http://127.0.0.1:8000/schema/swagger](http://127.0.0.1:8000/schema/swagger)

## Database
### To view the database diagram:
- go to [dbdiagram.io](dbdiagram.io)
- click `create your diagram`
- paste the content of `dbdiagram.txt` inside the left panel

### Basic structure
- The `recipes` table is the center of the database
    - It contains a description, prep and cook time, number of servings, and an owner (`owner_id` → `user`)
- Each recipe has a number of ingredients in `recipe_ingredients`
    - foreign key `recipe_ingredients.id` = `recipe.id`
- Each recipe_ingredient points to a food in `ingredients` and a unit in `units`
    - foreign key `ingredients.id` = `recipe_ingredients.ingredient_id`
    - foreign key `units.unit_id` = `recipe_ingredients.unit_id`
- Recipes can have `tags`, in `tag_categories`
    - foreign key `recipe_tags.id` = `tag.id`
    - foreign key `tag_category.id`= `tag.category_id`
- Users can keep recurring weekly groceries in `weeklygrocery`
    - each row has an `owner_id` → `user`, an `ingredient_id` → `ingredient`, a `unit_id` → `unit`, and a `quantity`

### How to
- Fresh setup (empty database): `uv run aerich init-db`
- After changing models in `src/models.py`:
    - `uv run aerich migrate --name [type_reason_here]`
    - `uv run aerich upgrade`
- The app applies pending aerich migrations automatically on startup (`src/database.py`).

## Development
### Tests
- Run the suite with `uv run pytest`
- HTTP tests use an in-memory SQLite database via autouse fixtures in `tests/conftest.py`; they apply the same aerich migrations and do not write to `src/recipes.sqlite3`
- If `init_db` runs during pytest while still pointed at `src/recipes.sqlite3`, the app raises an error instead of touching production data

### Formatting and hooks
- Python: `uv run ruff format` and `uv run ruff check` (`.py` files only)
- Optional pre-commit hooks: `uv run pre-commit install`, then `uv run pre-commit run --all-files`
