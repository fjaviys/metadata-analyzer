---
description: Updates CLAUDE.md's Gotchas, Architecture, and Conventions from recent corrections, then runs /insights to check whether the model/effort/roadmap configuration is still optimal
---

Keep this project's Claude Code configuration accurate and optimized over
time. Run this weekly, and any time you've just been corrected repeatedly
on the same thing. It has two parts: first reconcile `CLAUDE.md` with what
actually happened since the last commit, then check real usage against the
model/context roadmap.

## Part 1 — Reconcile CLAUDE.md with recent corrections

### 1. Gather the correction sources

- **This conversation**: correction instructions from the user ("don't do
  X", "that's wrong", "actually you need to..."), design decisions you
  changed after feedback, mistakes you had to fix more than once.
- **`git diff`** (staged + unstaged) and, if it exists, `git log -1
  --stat` of the last commit — to see which files actually changed, not
  just what was discussed.
- **`CLAUDE.local.md`**, if it exists and has content under "PR feedback"
  or "Personal quirks" — it may already contain corrections not yet
  reflected in `CLAUDE.md`.

If none of the above applies (a session with no corrections, no diff
since the last commit), say so and skip to Part 2.

### 2. Classify each finding

For every real correction or adjustment you find, decide which section of
`CLAUDE.md` it belongs to (use the headings already in the file; if none
fits, create one at the end):

- **Gotchas** — a concrete trap that caused or could cause an error:
  something that breaks next time if it isn't accounted for. Think in
  terms of the kind of project you have in front of you, for example:
  - **Web app / frontend**: SSR/CSR hydration ordering, race conditions in
    effects/reactivity, layout that breaks at a specific breakpoint,
    browser/CDN cache serving a stale JS bundle, cross-browser behavior
    differences, CORS when calling an external API.
  - **Android/iOS app**: lifecycle handling (rotation, process killed in
    background), permissions that must be requested at runtime, image
    densities that break layout on a specific device, OS
    background/battery policies, minimum SDK version that excludes an API
    in use.
  - **Landing pages**: Core Web Vitals (LCP/CLS) broken by a font or image
    missing dimensions, forms validating differently across browsers,
    duplicated or missing tracking/analytics, Open Graph metadata not
    refreshing after a cached deploy.
  - **Games**: render order/z-index hiding sprites, framerate varying by
    device and breaking physics, memory management for large assets, save
    state corrupting if closed mid-session.
  - **Backend/API**: race conditions on concurrent writes, migrations that
    break existing data, undocumented payload size/rate limits,
    inconsistent timezone or date format across layers.
  - **CLI/library**: API changes that break consumers without a major
    version bump, inconsistent exit codes, relative paths that depend on
    the invoking directory.
- **Architecture** — a design decision that changed during the review and
  is worth pinning down so it doesn't get accidentally undone in a future
  session (e.g. "chose X over Y because...").
- **Code and conventions** — a style, structure, or workflow rule that got
  corrected (naming, folder organization, how changes get tested before
  being called done).
- **CLAUDE.local.md** — if the correction is explicitly personal, or about
  how the user gives PR feedback, don't touch `CLAUDE.md`; it goes there
  instead.

If a finding wouldn't prevent a real future error, drop it — don't add it
"just in case".

### 3. Prune what's stale

Review the lines already present in Gotchas/Architecture/Conventions: if
any no longer applies (the code that caused it is gone, it was fixed at
the root and can't happen again, or a later change made it obsolete),
propose removing it in the same summary.

## Part 2 — Review usage against the model/context roadmap

### 4. Run /insights

Ask the user to run Claude Code's native `/insights` command (it analyzes
the last 30 days of sessions stored locally in `~/.claude/` — nothing
leaves their machine — and generates a report of friction areas, usage
patterns, and suggested `CLAUDE.md` rules) and share the report or its
main points with you.

### 5. Assess the report against the real configuration

- The `CLAUDE.md` rules `/insights` suggests: which are worth adopting as
  a Gotcha/Convention (same criteria as step 2), which are already
  covered, which don't apply to this project?
- Do the friction points reflect a mismatch between the model/`effort`
  configured in `.claude/settings.json` and the actual work? (lots of
  repeated corrections suggests the model is underpowered for those
  tasks; slow or expensive responses on simple tasks suggests the
  opposite)
- Do the usage patterns still match the roadmap in the "Model and context
  management" section of `CLAUDE.md` — same phases, same model per phase,
  same `/compact`/`/clear` thresholds? If the project has moved into a
  phase that isn't in the roadmap yet, or a phase's assumptions turned
  out wrong (e.g. "Documentation" needed Sonnet, not Haiku, because the
  domain was more subtle than expected), propose adding, removing, or
  re-assigning that phase's model — don't just add new phases on top,
  actively propose retiring ones that no longer apply.

## 6. Confirm before writing

Show a clear summary covering both parts: for each change, the target
file and section, whether it's an addition, a removal, or a model
reassignment in the roadmap, and the exact text (one line, in the same
concise style as the rest of the file — no nested bullets or paragraphs).
Ask with `AskUserQuestion`: "Apply all changes (recommended)" / "Choose
which to apply one by one" / "Cancel, don't touch anything".

If they choose "one by one", ask about each proposed change with
`AskUserQuestion` (yes/no) before including it.

## 7. Apply the changes

Use `Edit` on `CLAUDE.md` (and `CLAUDE.local.md` if applicable) — never
rewrite the whole file with `Write`. Add each line under the correct
heading, without duplicating lines that already carry the same meaning.
For `.claude/settings.json`, only change `model`/`effort` if the user
approved that specific change.

## 8. Final summary

List what was added, removed, or reassigned, by file and section. If
neither part found anything relevant, say so — don't force changes just
for the sake of having run the review.
