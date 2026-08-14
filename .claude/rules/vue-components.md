---
paths:
  - frontend/src/components/**/*.vue
---

Vue 3 `<script setup>` with TypeScript, styled with Tailwind utility classes.
There is no separate typecheck step — `npm run build` in `frontend/` is what
catches type errors.

## Selection and tree components

- **One source of truth for selection.** Keep the selected *leaves* (files) in a
  single reactive `Set` and derive folder checkbox state from it
  (`checked` / `indeterminate` via `:indeterminate.prop`). Never maintain a
  parallel set of selected folders — it desynchronizes the moment a single child
  is toggled, which is exactly the bug this rule exists to prevent.
- **Anchor ranges by identity, not index.** Shift-click ranges must anchor on a
  path, not a position in the visible list; collapsing a folder between two
  clicks shifts every index.
- **Whole rows are clickable**, not just the checkbox. Plain click replaces the
  selection, Ctrl/Cmd toggles one, Shift extends a range.

## Feedback

- Prefer computing the "after" state client-side when the data is already in the
  row (e.g. `filename_date` / `path_date` arrive with each analyzed file). It
  repaints instantly and needs no round trip. Persist in the background.
- Show origin → result → action on the row itself. If something the user asked
  for cannot be applied, say so **on that row** — never skip silently.
- Batch writes into one request rather than a sequential loop of per-item calls.

## Contract with the backend

`src/types/api.ts` mirrors the Pydantic schemas by hand and `src/api/client.ts`
is the only place that talks to the API. When an endpoint or schema changes, both
must be updated in the same change, and dead methods removed — nothing else keeps
them in sync.
