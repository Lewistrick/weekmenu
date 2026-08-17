# CSS & Template Reuse Rules

This project has a CSS design-token system and shared template primitives.
New code MUST use them. Do not duplicate what already exists.

## CSS: use tokens, never raw values

All colour, spacing, and radius values live in `src/static/css/tokens.css`.

- **Colours:** use `var(--token)`. Never write a raw `#hex` or `rgb()` in a rule.
  The only permitted raw hex values are DB-driven fallbacks inside an existing
  `var()`, e.g. `var(--tag-bg, #2563eb)`.
- **Spacing** (padding, margin, gap): use `var(--space-px)` through
  `var(--space-7)`. The scale is 0.125/0.25/0.5/0.75/1/1.25/1.5/2 rem.
  Snap to the nearest step; resolve ties downward.
- **Border-radius:** use `var(--radius-xs)` through `var(--radius-circle)`.
  Never write a raw `px` or `rem` radius.
- **Shadows:** use `var(--shadow-sm)`, `--shadow-md`, or `--shadow-lg`.

If no existing token fits, add a new one to `tokens.css` with a semantic name
before referencing it. Do not inline a magic value and plan to "tokenize later."

## CSS: use shared component classes

Shared classes live in `src/static/css/components.css`. Before writing a new
class, check whether one of these already covers the need:

- **Buttons:** `.btn` + modifiers (`.btn-primary`, `.btn-secondary`,
  `.btn-danger`, `.btn-ghost`, `.btn-sm`, `.icon-btn`).
- **Surface boxes** (cards, panels, editors): the `.surface` group rule. Any
  element with `border + --radius-md + --bg-surface` should compose with the
  existing surface rule, not redefine those three properties.
- **Chips/pills:** the `.chip` group rule (inline-flex + pill radius).
- **Forms:** `.form-group`, `.form-control`, `.form-actions`.
- **Inline confirm:** `.inline-confirm-wrap`, `.inline-confirm`,
  `.inline-confirm-trigger`, `.inline-confirm-cancel`, `.inline-confirm-label`.

If a new component is genuinely distinct, add it to `components.css`.
Feature-specific rules go in their feature file (`grocery.css`, `recipes.css`,
etc.), not in `components.css`.

## CSS: file organisation

`src/static/style.css` is a hub of 9 `@import` directives. Never add rules to
it directly. Place new rules in the correct feature file:

| File | Scope |
|---|---|
| `tokens.css` | `:root` custom properties only |
| `base.css` | body, links, shared primitives |
| `layout.css` | navbar, container, page grids |
| `components.css` | reusable UI components |
| `week-menu.css` | week-menu page |
| `grocery.css` | grocery list page |
| `recipes.css` | recipe views and edit page |
| `auth.css` | login/register |
| `admin.css` | admin pages |

## Templates: use shared partials and macros

### `editable_display` macro (`partials/_field_macros.html`)

For any "display value + edit button + scoped flash messages" pattern, use:

```jinja
{% from "partials/_field_macros.html" import editable_display %}
{% call editable_display(section_id, editor_endpoint, edit_label, edit_aria, scope, show_warnings=false) %}
  <p>{{ display_content }}</p>
{% endcall %}
```

The macro renders: caller content, then the hx-get edit button, then
flash-messages (and flash-warnings when `show_warnings=true`).
Do not hand-write this combination; use the macro.

### `inline-confirm.html` partial

For any "trigger button that reveals a confirm/cancel pair" pattern, use:

```jinja
{% with trigger_id="...", confirm_id="...", trigger_label=..., confirm_label=..., ... %}
{% include "partials/inline-confirm.html" %}
{% endwith %}
```

Two modes:
- **HTMX post:** pass `confirm_action`, `hx_target`, `hx_swap`.
- **Plain link:** pass `confirm_href` (skips the form, renders an `<a>`).

Optional: `trigger_icon` (only shown when truthy), `trigger_class` (defaults to
`grocery-clear-list-trigger`).

The toggle JS lives in `base.html` and works globally via event delegation on
`.inline-confirm-trigger` / `.inline-confirm-cancel`. Do not add per-page
toggle scripts.

### Flash messages

Always thread flash scope through the partial or macro that owns the region.
Do not add a bare `{% include "partials/flash-messages.html" %}` without a
`message_scope` when one is available. The `editable_display` macro handles
this automatically.

## General DRY enforcement

Before creating any new CSS class, partial, or inline HTML pattern:

1. Search `components.css` and `_field_macros.html` for an existing match.
2. Search the feature CSS file for a similar rule.
3. If a match exists, use it. Extend it with a modifier if needed.
4. Only create something new when no existing primitive covers the need.

When you spot duplication during a task (same 3+ CSS properties repeated, same
HTML structure in multiple partials), flag it and consolidate rather than
propagating the copy.
