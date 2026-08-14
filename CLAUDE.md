# Metadata Analyzer

Detects and repairs wrong or missing capture dates in photos and videos, then
optionally reorganizes them into date-based folders. Every destructive step is
opt-in, simulated first, backed up and verified.

# Code and conventions
- Stack: full-stack monorepo — FastAPI (Python) backend, Astro 4 + Vue 3 + Tailwind frontend, shared pure-Python engines in `shared/python/`
- Package manager: pip (`backend/requirements.txt`) for Python, npm (`frontend/package-lock.json`) for the frontend
- Tests: `.venv/bin/python -m pytest tests/ -q`
- Frontend build / typecheck: `cd frontend && npm run build`
- `exiftool` is an OS-level dependency (installed in the Dockerfile), never a pip package

# Workflow

## Non-negotiable (this project handles irreplaceable user photos)
- **Never write EXIF or move files without explicit user confirmation.** A real
  write requires `confirm_real_write=true`; dry-run is always available. Every
  real write takes a backup first and is re-read to verify afterwards.
- **Never fabricate a date.** If no reliable source exists, skip the file and
  report why. Completing partial precision (year → `YYYY-01-01`) is allowed;
  inventing a date is not.
- **Never commit or push without explicit permission, every time.** Approval for
  one commit does not carry over to the next. The same applies to long-running
  tasks.
- **Update `docs/SECURITY.md`** whenever behaviour with security or data-safety
  implications changes. It is the living record of those decisions.

## Day to day
- Run `.venv/bin/python -m pytest tests/ -q` before considering anything done.
  `pytest` is not on PATH — go through the venv.
- Run `npm run build` in `frontend/` after touching the frontend. It is the only
  thing that typechecks TypeScript and Vue here; there is no separate typecheck.
- Work on a branch, never push straight to `master`, and ask for review before
  merging.
- Use Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`).
- Check `/context` periodically; `/compact` past ~450k tokens, or `/clear` when
  the next phase does not depend on the previous one.
- Run `/optimus-claude-update-schema` roughly once a week to reconcile this file
  and the model roadmap with real usage.

# Model and context management

When entering a new top-level roadmap phase, ask permission to run
`/optimus-claude-update-schema` before continuing, so the roadmap is corrected by
real usage instead of staying frozen.

1. **Data-safety invariants** (what may be written/moved, under what guarantees) → **Opus**; a mistake here corrupts unrecoverable photos. `/context` when closing the phase.
2. **Destructive engines** (`correction_engine`, `reorganize_engine`, backup/undo) → **Opus**. `/compact` on entry — depends on phase 1.
3. **Features and UX** (API, services, Vue components) → **Sonnet**, the bulk of the work. `/compact` past ~450k tokens.
4. **Tests and verification** → **Sonnet** to write them, **Haiku** to run and report. `/compact` if still on the same feature.
5. **Documentation** (`SECURITY.md`, `DEPLOYMENT.md`, README) → **Haiku**. `/clear` on entry.
6. **NAS deploy / Docker / CI** → **Sonnet**; escalate to **Opus** if a deploy failure resists. `/clear` on entry.

# Architecture
- `shared/python/` — pure, dependency-free engines, importable without FastAPI:
  `metadata_analyzer` (exiftool driver), `date_detector` (all date detection),
  `correction_engine` (EXIF writes), `reorganize_engine` (file moves),
  `database_manager` (SQLite), `report_generator` (PDF). Keep them framework-free.
- `backend/` — `api/` routers, `services/` orchestration, `core/` (security,
  config, logger, exceptions), `schemas/` Pydantic models, `database/`.
  Services build plans; engines execute them.
- `frontend/` — Astro pages with Vue islands (`client:load`). `src/api/client.ts`
  is the single API surface; `src/types/api.ts` mirrors the Pydantic schemas by
  hand and must be updated alongside them.
- `tests/` at the repo root, run from the root.
- User-facing flow is three independent steps: `/analysis` (read-only) →
  `/corrections` (step 1, metadata) → `/reorganize` (step 2, folder structure).

# Gotchas
- **FastAPI route order:** literal routes (`/gate`, `/preview`, `/file-overrides`,
  `/layout-presets`, `/runs`) must be declared *before* dynamic `/{run_id}` routes,
  or the dynamic one swallows them and returns a bogus 200.
- **A real correction invalidates its analysis session.** `has_real_corrections()`
  gates `/reorganize` with a 409 until the folder is re-analyzed — session rows no
  longer reflect what is on disk.
- **`filename_date` / `path_date` are precomputed at analysis time** and already
  EXIF-formatted. Step 1 reads those columns; it does not re-detect on demand.
- **A folder name is only "a date" if the date covers the whole name.** `2009`,
  `20090802`, `2009-08` get peeled; `vacaciones 2009` is a *root* and is kept.
  Matching an embedded date anywhere in the name silently destroys user-chosen
  folder names.
- **Accepted debt, do not "fix" by migrating:** the `path_overrides` and
  `folder_decisions` tables remain in the schema with no active CRUD. They are
  left in place to avoid a risky `ALTER TABLE` on existing databases.
- **`data/` is gitignored** and holds the SQLite DB, backups and logs — real user
  data. Never commit anything from it.
- The media mount is `read_only: true` by default in `docker-compose.yml`, so a
  correction physically cannot write until that is deliberately changed to `:rw`.

> Boris's rule: if a line in this file doesn't prevent a real error, cut it.
