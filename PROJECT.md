# ForgeModding — constitution

<!-- Project-owned, no BASE regions. This is the file every generic skill reads FIRST:
     one generic skillset, per-project behavior. Keep it short and current — when the
     project's direction changes, this file changes in the same session. -->

## Goal

Author and maintain MTG Forge Adventure Mode content — and the engine patches some of it needs — as a standalone, deployable mod repo.

ForgeModding is the source of truth for MTG Forge Adventure Mode content: planes (enemies, items, quests, points of interest, decks, sprites, maps), Adventure-only and constructed custom cards, and the tooling that deploys and validates them. The Forge install is treated as a disposable render target — content is deployed into it by junction on PC and by push on Android, never authored inside it.

A second, smaller track carries Java engine patches as a `git format-patch` series against a pinned upstream commit, for the content types Forge's closed data enums genuinely cannot express (new *kinds* of item effect, quest objective, reward, or dialog action). Everything the data layer can reach stays in the data layer; the engine track is the exception, not the default.

## Non-goals

- **Not a Forge install mirror.** Stock content is referenced by path, never copied in. Any file shipped here is a permanent fork of *that file*; any asset **path** referenced is free. The install stays disposable.
- **Not an upstream contribution pipeline.** Content and patches are built for local use, not maintained as PRs against `Card-Forge/forge`. Because a plane is a self-contained folder, upstreaming would be a copy and a commit rather than a rebase — so declining this now costs nothing later.

Deliberately **not** listed as non-goals, so the record is unambiguous: Java engine work is **in scope** (see [docs/ENGINE.md](docs/ENGINE.md)), and Android parity for engine features is a **deferred milestone**, not an exclusion.

## Users

Me. Single-author repo. The docs are written for a future me returning after an upstream snapshot bump — not for a public contributor audience — which is why the fork ledger and the evidence tags matter more here than onboarding prose.

## Quality bars & definition of done

- A change is done when: it's implemented, its mapped docs are current (see the documentation contract below), and the verify method below has actually been run with its output checked.
- **Preview and approve before writing.** A new plane, a new content system, or a new engine patch gets its shape agreed before the files exist.
- **Claims carry evidence tags**, as the founding assessment does: **[F]** verified against files in this install · **[B]** decompiled from bytecode · **[D]** stated in Forge's shipped docs · **[I]** inferred, not yet tested. An `[I]` claim is not evidence and no rule may rest on one.
- **A content change is not done until the linter has run and its report been read.** Forge's failure mode for bad content is silent fallback, not an error — the game will happily load a plane where half your work is invisible.
- **An engine patch is not done** until it re-applies cleanly to the pinned upstream commit *and* something under `planes/` or `custom/` actually consumes it.

## Verify method

One entry point, two tracks. `tools/verify.py` always runs the content linter over `planes/` and `custom/`; when `engine/` has changed it additionally checks that the patch series still applies to the pinned upstream commit and builds.

Prerequisites it cannot find (Maven, the Forge workspace clone, `adb`) are reported as **BLOCKED** with the missing tool named — never skipped silently. A linter that quietly does less than it claims is worse than no linter, because it turns an unchecked repo into one that *looks* checked.

Checks not yet implemented are listed by name in the report's own output, so the gap between what the linter promises and what it does stays visible on every run instead of being buried in this file.

- Command: `python tools/verify.py > verify-report.txt`
- Evidence: `verify-report.txt` <!-- the on-disk artifact whose freshness proves a run happened; "none yet" leaves the check-verify hook dormant (doctor reports that) -->
- Exempt: `**/*.md` <!-- pure-docs/wording patterns that skip the gate -->

## Documentation contract

<!-- Which documents the user reads to know this project's state, and what each one
     promises its reader. Mirrored mechanically in .claude/base-manifest.json doc_map
     (source globs -> doc), which drives the check-doc-freshness hook. -->

| Document | What it promises its reader |
|---|---|
| `README.md` | What this is, current status, how to run + verify it |
| `docs/ARCHITECTURE.md` | The two-track model, how content reaches the install and the device, and why the engine track ships patches rather than a fork. |
| `docs/ENGINE.md` | The Java track end to end: workspace bootstrap, the patch-series workflow, re-applying after an upstream snapshot, and which content types actually require Java. |
| `OWNERSHIP.md` | Every file forked from `common/` with the upstream build it was forked at, and the engine series' pinned commit — the ledger that turns a future upstream bump from archaeology into a diff. |

## References summary

- **Forge offline docs** (`forge-docs`) — the shipped wiki mirror. First stop for any schema or tutorial question, and more complete than the website.
- **`common/` fallback layer** (`forge-common`) — every stock asset this repo references by path. Read constantly, modified never: editing a stock tileset changes every map in every plane.
- **Card script corpus** (`forge-card-corpus`, `forge-token-corpus`) — 33,696 card scripts and 839 token scripts. The corpus is the real documentation for the card DSL.
- **Forge upstream** (`forge-upstream`) — the live repo: snapshot churn, the source of the engine pin, and the escalation target when the local install cannot answer.

Local paths are bound per-machine in gitignored `references.local.json`; this repo is public and carries none of them. The engine **workspace** clone is deliberately *not* a reference — it is a mutable build area; see [docs/ENGINE.md](docs/ENGINE.md) for the rule that protects it instead.

## Open direction notes

- **M1 — prove the content pipeline end to end.** The seven-file "Proving Plane" from the assessment's §10, run against gates G1–G7. Zero art required: every visual asset is borrowed by path, which also *proves* the fork-cost rule. This converts most `[I]` claims in the assessment to `[F]`, and lands before any engine work.
- **R1 first, ahead of authoring anything real.** Open `items.json` in the Adventure Editor, save with no changes, `git diff`. The junction hands the editor write access to this repo, so a lossy round-trip would be discovered late and painfully. Highest-impact unknown in the assessment.
- **M2 — bootstrap the engine workspace.** Install Maven, clone `Card-Forge/forge` outside this repo, pin the commit, and get one *unmodified* build running on PC before any patch exists. Open `[I]`: JDK 26.0.2.1 is installed on this machine but has not been verified against Forge's target Java version.
- **M3 — first engine patch**, chosen to unlock a content type the data layer genuinely cannot reach, with the failed data-layer approach recorded alongside it.
- **M4 (deferred)** — Android APK pipeline: Android SDK + Maven + keystore, per Forge's `docs/Development/Android-Builds.md`. Until then engine features are PC-only while content stays dual-platform.
- **Machine gaps to close** (`/base:repo-setup`'s preflight will keep naming these): `mvn` not installed, `adb` not installed, no engine workspace clone.
- **Before any public release of content**, resolve licensing and asset provenance — Forge's licence, MTG IP, and any third-party art. This repo is public; that question gets answered before content ships, not after.
- **Known divergence, accepted knowingly:** `docs/FORGE_MODDING_ASSESSMENT.md` contains absolute machine paths (`E:\Programme\MTGForge`, `E:\Projekte\ForgeModding`), which the seeded doctrine header bans from version control. Kept because they are part of that document's evidence — it measures one specific install at one specific build — and they leak no username or account data; its `%APPDATA%` / `%LOCALAPPDATA%` references are already env-var forms. Revisit if this repo ever takes outside contributors.
