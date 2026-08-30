# ForgeModding — project rules

Author and maintain MTG Forge Adventure Mode content — and the engine patches some of it needs — as a standalone, deployable mod repo.

<!-- BASE:doctrine-header:v1 START -->
This repo was created from **ClaudeBase** (the version at creation, and the last synced one, are recorded in `.claude/base-manifest.json`). The generic machinery — setup, audits, sync, harvest — arrives via the `base` plugin and updates with it; this file and the other seeded docs are owned by this project, except the `BASE:` marker regions, which `/base:sync` maintains (never hand-edit inside them — needing to is a missing-interview-question bug in Base, file it as a lesson). `/base:doctor` shows status. No personal data in version control: no real names, emails, machine-specific absolute paths, or session IDs — machine-local state lives in gitignored `*.local.*` files.
<!-- BASE:END -->

## What this project is

See [PROJECT.md](PROJECT.md) — the constitution: goal, non-goals, quality bars, verify method, and the documentation contract. Generic skills read it first; keep it current when direction changes.

## The hard rule: external references are read-only

This project's declared ground truths are registered in [REFERENCES.md](REFERENCES.md).

<!-- BASE:doctrine-references:v1 START -->
**Read freely, write never — at every entry point.** Each reference's access method and comparison procedure live in REFERENCES.md; the `protect-references` hook blocks writes to declared paths. If a task seems to require editing a reference, **stop and warn the user instead of proceeding**, even if only part of a larger task touches it. A deliberate exception is made by flipping `modules.references` off in `.claude/base-manifest.json` — a visible, logged act — never by quiet edits.
<!-- BASE:END -->

<!-- BASE:doctrine-writeback:v1 START -->
## The highest-priority standing task: turn every lesson into a *rule*, not a war story

**Improving this project's workflow, skills, and docs with what a task teaches is the single most important recurring job — above finishing any individual feature.** A lesson only counts once it's written as a **prescriptive rule that tells the next session what to DO**, not a "gotcha" describing what went wrong. The test: *could someone follow this without already knowing the story behind it?*

When writing a finding back:
1. **Lead with the imperative** — a step someone executes.
2. **Include the verification step** if the failure was "I thought I had done it right" — an instruction that can be silently satisfied wrongly needs a check that proves it was satisfied.
3. **Keep the evidence, demote it** — `file:line`, exact error text, sample size N — *after* the rule, never in place of it. Record failed approaches too; they're the expensive knowledge to rediscover.
4. **Prefer removing the choice over documenting the hazard** — a helper that can't be called wrongly beats any warning text.

The escalation ladder for a recurring failure: prose warning → imperative rule + verification step → audit detection recipe → hook. A rule that gets violated *after* being written down is evidence the writing was in the wrong **form**, not that people need reminding.

**Every written-back lesson also gets a `.claude/learning-log.md` entry in the same edit**, tagged `scope: generic|project` with an `applications:` date list (the log is the harvest index, never the rule's home). A `generic` lesson applied 2+ times is a `/base:promote` candidate — that's how improvements discovered here reach ClaudeBase and every sibling project. Needing to hand-edit a Base-owned file or `BASE:` region is itself always a `generic` lesson ("Base is missing an option/question").
<!-- BASE:END -->

<!-- BASE:doctrine-docs:v2 START -->
## Documentation is the user interface of this project

The user reads this project's state through the docs named in PROJECT.md's documentation contract. **A change to a mapped source area isn't done until its mapped doc is current** — same weight as the verify gate; the `check-doc-freshness` hook nudges on the manifest's `doc_map`. Rules:
- `AUTO:` regions in docs are generated — never hand-edit inside them; content that must survive regeneration sits outside the markers.
- Root README and contract docs are **not** create-late: they exist from day one and stay current without asking. Optional deep-dive docs are create-late-ask-first; but once one exists, keep it current, don't ask again.
- A new skill/doc file, or a structural edit to one, isn't done until a scoped `/base:doc-audit` cold-test covers the changed files (wording-only fixes exempt). One convention, one home: an index/checklist row links to the owning doc, never restates it.
- Authoring or restructuring a project skill follows `/base:skill-author` (two-tier SKILL.md + `references/` split by content shape, reference-index table, description-line triggers, no confusable names next to `/base:*` skills).
- Documented reversals stay in place, marked as reversed with the reason — a retired idea that vanishes gets re-derived.
- Derive, don't enumerate: no doc or hook hardcodes a list (of modules, files, features) that the manifest or the tree can supply.
<!-- BASE:END -->

<!-- BASE:doctrine-verify:v1 START -->
## Nothing is "done" untested

Every change inside the manifest's `source_globs` ends with the verify method from PROJECT.md actually run and its output checked before being reported as done — silent breakage is common and doesn't always error loudly. Proportionality: changes matching `verify.exempt_patterns` (pure docs/wording) skip this, but a mixed edit that also touches source doesn't. Evidence standard for any claim written back: `file:line`, the exact error text (the next person greps for that string), and sample size N when the conclusion rests on frequency.
<!-- BASE:END -->

## Project-specific rules

### Content

- **Reference stock assets by path; fork a shared file only when you actually must** — and add its `OWNERSHIP.md` row, carrying the install's `build.txt` timestamp, **in the same edit**. Verification: after any change under `planes/`, no file newly present in your plane may also exist in `common/` without a matching `OWNERSHIP.md` row; `tools/verify.py` checks exactly this. *Evidence: fallback is whole-file with no merge — `Realm of Legends` forked `enemies.json` (956 entries) and forfeited all 464 of common's, while borrowing sprites from common's 493 atlases by path.*
- **Never edit content under the Forge install directly.** The install is a disposable render target; this repo is the source of truth and `tools/deploy.py` is the only path in. Verification: the deployed plane must be a reparse point, not a real directory — `tools/deploy.py` asserts this and repairs it. *Evidence: the installer overwrites the install directory, and `res/` is the one path `forge.profile.properties` cannot relocate.*
- **Run `tools/verify.py` and read its report before launching Forge** after any content change. *Evidence: Forge's failure mode for bad content is silent fallback, not an error — a plane with an unresolvable sprite, deck or card name loads happily and simply shows less than you authored.*
- **End every content change with a paste-ready F9 console command** (`spawn enemy <name>`, `give item <id>`, `give quest <id>`). Commands are case-sensitive. *Evidence: JSON edits and plane switches both require a relaunch; the console is what keeps a 3-minute loop tolerable.*

### Engine

- **Exhaust the data layer before writing Java.** For card mechanics use the `Named$ <Yourword>` escape hatch, matched by `Activated.NamedAbility<Yourword>` and queried via `Count$FromNamedAbility<name>`; for content, recombine existing objectives and `union` rewards before adding a type. Verification: an engine patch proposal must name the data-layer approach that was tried and why it failed. *Evidence: Forge's own docs invent "Meditate" and "Paranoia" entirely in script. A Java patch is a maintenance cost re-paid at every upstream snapshot; a data solution is free.*
- **Record every patch in `engine/PINNED.md` with the closed set it extends and the content type it unlocks.** A patch that no content under `planes/` or `custom/` consumes does not ship. *Evidence: the closed sets are `EffectData` (~12 fields), `ObjectiveTypes` (26), reward `type` (7), and the dialog action/condition enums (21 / ~14).*
- **Never commit to an upstream branch in the engine workspace.** All work lives on the `forgemodding` branch and leaves as exported patches. The workspace is deliberately *not* a declared read-only reference — it is mutable by design — so this rule is what protects it, instead of the `protect-references` hook.

### Both tracks

- **Tag every claim**: `[F]` verified in this install · `[B]` decompiled · `[D]` from Forge's shipped docs · `[I]` inferred and untested. An `[I]` claim may not be the basis of a rule. Open `[I]` claims live in the assessment's §11 verify log and are tracked state until answered.
