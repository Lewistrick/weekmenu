# CSS & Partials Refactor Plan

Goal: move from page-specific CSS classes to a small, reusable design system so
the app feels consistent everywhere, and fold the most repetitive HTMX partials
into a few generic building blocks.

Status: **Phase 1 (CSS color tokens) DONE.** Everything else is not started.

Phase 1 result: `:root` added with 53 tokens; all 51 remaining hex literals are
either token definitions (39) or per-user DB colour fallbacks (12,
`var(--tag/shop-*, #...)`, deliberately kept). Zero raw colour literals remain in
the rules. Three intentional consolidations to watch: success flash
(`.single-message`) now uses the success palette, the amber clear-list button
folded onto the `--warn*` tokens, and the toggle "on" green is now `--success`.

---

## Why (measured diagnosis)

- **No design tokens at all.** `src/static/style.css` is a flat 2347-line file
  with **58 distinct hex colors** plus many one-off `rgba()` values. Among them:
  9 different "text gray" shades (`#ddd #d8d8d8 #d4d4d4 #cfcfcf #c8c8c8 #b5b5b5
  #aaa #999 #8f8f8f`) and 6 near-identical surface grays. Same intent, different
  values, chosen by eye.
- **No spacing scale.** ~20 distinct padding/margin/gap values
  (`0.35 0.45 0.55 0.65 0.85rem` and so on).
- **Feature-scoped components.** `btn-action--grocery`, `shop-chip-btn`,
  `tag-group-chip`, `icon-btn`, `nav-link` each re-solve "a button" or "a chip"
  separately, which is why the look drifts from page to page.
- **63 partial templates / 123 route handlers**, inflated by one repeated
  pattern (inline field editing rendered as server fragments) and by every
  partial hand-threading its own flash-message block.

Good news: the bones are clean (controller/service split, BEM-ish modifiers
already used like `.nav-link--muted`), so this is consolidation, not a rewrite.

---

## Part 1 - CSS: page-specific -> reusable system

### Target structure

For now keep a **single** `src/static/style.css` served as today (no change to
`base.html` or the static route). Organize it internally into clearly banded
sections; a physical split into a `css/` folder is deferred to Phase 4.

1. **Tokens** - a `:root` block, the single source of truth (colors now;
   spacing/radius added in Phase 2).
2. **Base** - reset, `body`, typography, links, tables.
3. **Components** - the reusable vocabulary, each defined once: `.btn` (+
   variants), `.form-group`/`.form-control`/`.form-actions`, `.panel`/`.card`,
   `.chip` (absorbs tag/shop/status pills), `.data-table`, `.inline-confirm`,
   `.actions-row` + a few spacing utilities.
4. **Layout** - navbar, container, page grids.
5. **Features** - genuinely unique page rules, now consuming tokens not raw hex.

The runtime `var(--tag-bg, #2563eb)` / `var(--shop-bg, ...)` variables are **data**
(per-user colors from the DB) and stay exactly as they are.

### Phase 1 - Introduce color tokens (THIS PHASE)

Define a semantic `:root` palette and replace every raw color literal with a
`var(--token)`. Because the user has approved minor visual changes for the sake
of consistency, near-duplicate colors are collapsed onto one token (this is the
consistency win). Colors only; spacing/radius/components come later.

Proposed `:root` (dark theme, ~40 tokens replacing 58 hexes + rgba sprawl):

```css
:root {
  /* Backgrounds */
  --bg-body: #333333;              /* page */
  --bg-chrome: #222222;            /* navbar */
  --bg-surface: #3d3d3d;           /* cards, panels, days, items, editors (absorbs #3a3a3a) */
  --bg-surface-alt: #2f2f2f;       /* dropdown menus, export box, unit chip (absorbs #2a2a2a/#2b2b2b) */
  --bg-raised: #444444;            /* list rows on the body (absorbs #454545) */
  --bg-inset: #353535;             /* row on a coloured shop panel, search popover */
  --bg-control: #4a4a4a;           /* icon/secondary buttons, idle chips (absorbs #4d4d4d) */
  --bg-control-hover: #555555;
  --veil-light: rgba(255,255,255,0.06);   /* subtle hover wash (absorbs 0.05) */
  --veil-border: rgba(255,255,255,0.12);
  --veil-chip-border: rgba(255,255,255,0.15);

  /* Borders */
  --border: #555555;               /* default (absorbs #4d4d4d) */
  --border-strong: #666666;        /* inputs, medium emphasis */
  --border-hover: #777777;         /* hover (absorbs #888888) */
  --border-subtle: #444444;

  /* Text */
  --text: #dddddd;                 /* body (absorbs #d8d8d8 #d4d4d4 #cfcfcf) */
  --text-strong: #f2f2f2;          /* headings, brand (absorbs #f0f0f0) */
  --text-heading: #e8e8e8;         /* section titles, list text (absorbs #e0e0e0) */
  --text-muted: #b5b5b5;           /* hints, labels (absorbs #c8c8c8 #aaa) */
  --text-subtle: #999999;          /* placeholders, faint ids (absorbs #8f8f8f) */
  --text-invert: #ffffff;          /* on-accent, hover white */

  /* Accent (brand blue) */
  --accent: #5a9fd4;
  --accent-hover: #4a8fc4;
  --accent-ring: rgba(90,159,212,0.20);
  --accent-veil: rgba(90,159,212,0.15);
  --link: #b8d9f0;                 /* light-blue links & amounts (absorbs #8ec8ff #b8dcff) */
  --brand-blue: #2563eb;           /* export gradient + DB colour default */
  --brand-blue-dark: #1d4ed8;
  --brand-blue-light: #3b82f6;

  /* Success (green) */
  --success: #22c55e;
  --success-strong: #16a34a;       /* absorbs #28a745 #15803d */
  --success-border: #4d7a4d;
  --success-bg: rgba(40,167,69,0.12);
  --success-text: #86efac;

  /* Warning (amber) */
  --warn: #d97706;
  --warn-strong: #b45309;
  --warn-bright: #f59e0b;
  --warn-text: #fbbf24;            /* absorbs #fde68a #ffe08a */
  --warn-border: #d4a017;
  --warn-bg: rgba(255,193,7,0.12); /* absorbs 0.10 / 0.18 */
  --warn-bg-strong: rgba(217,119,6,0.20);

  /* Danger (red) */
  --danger-border: #a94442;
  --danger-border-hover: #c9302c;
  --danger-text: #f5b7b1;
  --danger-bg: rgba(169,68,66,0.20);

  /* Shadows & overlay */
  --shadow-sm: 0 2px 8px rgba(0,0,0,0.25);
  --shadow-md: 0 6px 16px rgba(0,0,0,0.35);
  --shadow-lg: 0 10px 30px rgba(0,0,0,0.35);
  --overlay: rgba(0,0,0,0.9);
}
```

Text-gray consolidation map (the biggest source of drift):

| Old | New token |
|-----|-----------|
| `#ddd #d8d8d8 #d4d4d4 #cfcfcf` | `--text` |
| `#e8e8e8 #e0e0e0` | `--text-heading` |
| `#f2f2f2 #f0f0f0` | `--text-strong` |
| `#c8c8c8 #aaa` | `--text-muted` (`#b5b5b5`) |
| `#999 #8f8f8f` | `--text-subtle` |

### Phase 2 - Unify the spacing / radius scale

Add `--space-1..6` (`.25 .5 .75 1 1.5 2rem`) and `--radius-sm/md/pill`; snap the
~20 spacing values and the radius set (`4/5/6/8/10/12px`, `999px`) onto them.
This phase has small intentional visual nudges, so it wants an eyeball review.

### Phase 3 - Consolidate components (one at a time, one commit each)

Buttons first (make `.btn` the real definition, fold `btn-action--*`,
`shop-chip-btn`, `icon-btn` onto it), then chips, then forms, then tables.

### Phase 4 - Delete dead selectors + optional file split

Remove orphaned page-specific rules once features route through shared
components; optionally split `style.css` into a `css/` folder with `@import` or
multiple `<link>` tags.

### Test safety (CSS)

The ~270 tests assert on HTML, not CSS. Changing color values and folding rules
breaks nothing as long as class **names** the DOM uses are preserved. Each phase
is its own reviewable, revertible commit.

---

## Part 2 - Partials: fold the repetitive ones

Direct answer: no, they do not each need their own partial. Two patterns cover
most of the sprawl.

### A. Inline confirmation -> one shared partial

`partials/grocery-inline-confirm.html` is already generic (takes `trigger_id`,
`confirm_action`, `confirm_label`, `trigger_icon`, ...); it is just grocery-
branded. Promote it to `partials/inline-confirm.html`, lift the hardcoded
`hx-target="#grocery-list-body"` / `hx-swap` into `target` / `swap` params, and
swap `grocery-*` classes for the shared `.inline-confirm` component. Then
`delete-confirmation.html` and any future "are you sure?" reuse it.

### B. Inline field editing -> one macro pair

The `edit-*` / `edited-*` field partials (title, desc, image, servings) are
near-identical; they differ only in display tag/class, input type, field name,
two endpoints, and a scope string. Replace with a Jinja macro file
`partials/_fields.html`:

- `editable_display(field_id, display_html, edit_endpoint, scope)` - value +
  edit button + flash include; `display_html` passed via `{% call %}` so `<h2>`
  vs markdown `<div>` share the wiring.
- `field_editor(field_name, value, input_type, save_endpoint, target)` - the
  little form, input chosen by `input_type`.

Folds ~8 partials into 2 macros and lets the four `*-editor` GET + four `edit-*`
POST handlers in `recipes.py` become a small table-driven config.

### C. Kill repeated flash plumbing

Almost every partial ends with
`{% with message_scope=... %}{% include "partials/flash-messages.html" %}{% endwith %}`.
Move flash messages to one out-of-band region (`hx-swap-oob="true"`) so handlers
push into a single `#flash` element and no partial carries its own scope.

### What NOT to touch

Genuinely unique views keep their own partials: `week-menu-content.html`,
`grocery-list-panel.html`, admin translation tree nodes. Fold the repeated
mechanical partials, do not over-abstract unique views.

### Test safety (partials)

Keep output HTML equivalent (same visible text, same `hx-*` behavior) so most
tests pass untouched; update the few that assert exact structure. Per project
rule, add a test pinning each shared macro/partial's behavior.

---

## Order of attack

1. CSS Phase 1 (color tokens) - biggest consistency win, lowest risk. **<- now**
2. Partial B (field-editor macros) - retires the most partials, declutters `recipes.py`.
3. Partial A (shared inline-confirm) + C (OOB flash) - small, high leverage.
4. CSS Phases 2-4 - incremental component consolidation.

Each item is an independent, test-backed commit.
