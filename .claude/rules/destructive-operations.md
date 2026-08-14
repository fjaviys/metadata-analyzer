---
paths:
  - shared/python/*_engine.py
  - backend/services/**/*.py
---

This code decides what happens to irreplaceable user photos and videos. Hold it
to a higher bar than the rest of the project.

## Invariants that must survive every change

- **Never fabricate a date.** No reliable source → skip the file and report the
  reason. Enforce it in the engine, not only at the API boundary: validation can
  be bypassed by a direct DB write, the engine cannot.
- **Real writes are opt-in.** `confirm_real_write=true` or reject (428). Dry-run
  must stay reachable and must not touch disk on any path, including error paths.
- **Backup, then write, then verify.** Re-read what you wrote; revert that file
  from backup if it does not match. Never trust the write succeeded.
- **Moves are recorded** in `reorganize_moves` so a run can be undone as a unit.
- **Collisions get a suffix.** Never overwrite an existing destination.
- **Cross-device moves** copy, verify size, then delete — never fail halfway.
- **Abort restores.** If the failure ratio exceeds the threshold, undo what was
  already applied. A half-applied run is worse than a failed one.

## Boundaries

- `shared/python/` stays framework-free: no FastAPI, no settings imports, no
  request objects. Engines must be importable and testable standalone.
- Services build plans; engines execute them. Keep planning pure and side-effect
  free — that is what makes preview endpoints safe to expose.
- Every path goes through `core/security.py`. Be especially careful with computed
  destinations: folder-peeling must never escape the analyzed root.

## When changing behaviour here

Add or update a test that pins the invariant — for destructive code, "it works
now" is not evidence. Then update `docs/SECURITY.md`: it is the living record of
why each guarantee exists, and a change that alters a guarantee without updating
it is incomplete.
