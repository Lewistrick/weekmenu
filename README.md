# Weekmenu

## Usage
### To start the app
- `uv run litestar --app src.app:app run -r`
    - (remove `-r` when not editing the code)

### Accounts and login
- The app requires an account. Visiting any page while logged out redirects to the login page.
- Create an account at `/register` with a username, a password (min. 6 characters), and an optional email address. Registering logs you in automatically.
- Log in at `/login` and log out from the "🚪 Log out" item in the ⚙️ Settings menu.
- Manage your account at `/profile` (reachable via ⚙️ Settings → 👤 Account): update your email, language, default week-menu servings, change your password, or delete your account (which removes the account and its recipes).
- Passwords are hashed with bcrypt and the logged-in user is tracked in a signed cookie session.
- The first account to register inherits any pre-existing recipes from an older single-user database (existing data is not lost).

### Recipe sharing and privacy
- Every recipe has an **owner** (who controls it), a **creator** (who originally wrote it), and a private/public flag (toggle on the edit page). New recipes start private with you as both owner and creator.
- You always see and manage your own recipes. You can also open other users' **public** recipes (read-only) via direct links or search when you opt in.
- By default, recipe search, the random **private** recipe picker, listings, and week-menu tools only use **your own** recipes. Check **Include public recipes** on the search or week menu page to also show other users' public recipes in those tools.
- Use **Random public recipe** to jump straight to a random public recipe owned by another user.
- Import a public recipe you do not own with **Import to my recipes** on its view page. This creates a private copy in your collection, keeps the original creator credited, and blocks importing the same public recipe twice.
- Trying to edit or delete a recipe you do not own returns a 404.

### Per-user week menu
- Your week menu, start day, tag constraints, and grocery list are stored per user in the session, so logging out and into another account on the same browser shows that account's own plan rather than the previous user's.
- Week menu randomization and per-day recipe search use your own recipes by default; enable **Include public recipes** in the week menu toolbar to widen the pool.
- New empty week-menu slots use your profile setting for default servings.

### Per-user settings files
- Account settings are stored as JSON files in `user_settings/{user_id}.json` in the project root.
- Each file stores:
  - `language` as a full language label prefixed with a flag (for example: `🇳🇱 Nederlands`)
  - `servings` as the default servings value used when week-menu day slots are empty
- Settings are editable from `/profile` under the **Settings** section.

### Per-user catalog (ingredients, units, tags, shops)
- Ingredients, units, tag groups, tag values, and shops belong to an account. You only see and manage your own catalog data in lists, forms, and API responses.
- Registering a new account seeds a default unit set: `g`, `kg`, `ml`, `l`, `dl`, `el`, `tl`, `st`, `pcs` (with singular/plural labels where applicable).
- Unit abbreviations are unique per user (`owner` + `abbrev`), not globally.
- When you import a public recipe, its ingredients, units, and tags are remapped into your catalog (matched by name where possible) so edits stay isolated from the original author's data.
- Legacy single-user data is assigned to the first registered account on startup; duplicate unit abbreviations for that account are merged during the one-time backfill.

### What will it be able to do
- Compose your own cookbook
- Organize recipes with tag groups and values (for example: season, carb type, diet)
- Create a random week menu, giving you a random recipe for each day of the week
    - Optional tag constraints when randomizing: same tag for every day, vary tags across the week, or at least N days with a chosen tag
    - Reorder meals by moving a day's recipe up or down the week
    - Enter the number of servings for each day; amounts are scaled from each recipe's own serving count
- Generate a grocery list from the week menu
    - Ingredient quantities are scaled to each day's servings, then ingredients sharing the same name and unit are added together
    - Open it from the "🛒 Grocery list" button on the week menu page (`/week-menu/grocery-list`)
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

### How to
- To initialize: `uv run aerich db-init`
- To migrate to new version:
    - `uv run aerich migrate --name [type_reason_here]`
    - `uv run aerich upgrade`

## Development
### Tests
- Run the suite with `uv run pytest`
- HTTP tests use an in-memory SQLite database via autouse fixtures in `tests/conftest.py`; they do not write to `src/recipes.sqlite3`
- If `init_db` runs during pytest while still pointed at `src/recipes.sqlite3`, the app raises an error instead of touching production data

### Formatting and hooks
- Python: `uv run ruff format` and `uv run ruff check` (`.py` files only)
- Optional pre-commit hooks: `uv run pre-commit install`, then `uv run pre-commit run --all-files`
