# ForgeModding — external references & ground truths

**Every reference here is read-only: read freely, write never, at every entry point.** The `protect-references` hook blocks writes to declared paths; a deliberate exception is flipping `modules.references` off in `.claude/base-manifest.json` (visible, logged), never a quiet edit. If a task seems to require changing a reference, stop and warn the user.

This file is the single source of truth for references. The manifest's `readonly_refs` mirror is **generated from the entry frontmatter blocks below** — at scaffold time by `/base:new-project`, and re-derived by `/base:repo-setup` step 3 whenever references are (re)bound. Never hand-edit the mirror; `/base:doctor` check 10 and `/base:doc-audit` both check agreement. Machine-local paths live in gitignored `references.local.json` (`{"<id>": "<absolute local path>"}`) **at the repo root** — that exact location is where the hooks look, and a copy under `.claude/` is silently ignored, leaving every local reference unguarded. Bound per-machine by `/base:repo-setup`.

## Ground-truth routing

<!-- When project knowledge comes up short, this table says where the authoritative
     answer for each domain lives and how to escalate when the primary source runs out.
     Whatever you learn there gets written back into the owning doc/skill in the same
     session, with its evidence — an un-written-back finding is unfinished work. -->

| Domain / question | Reference | Access method | Escalation when it runs out |
|---|---|---|---|
| How does this Adventure JSON schema / feature work? | `forge-docs` | `Read <forge-docs>/Adventure/*.md` | The Adventure Editor's own field set, then `forge-upstream`'s wiki |
| What does a stock enemy / item / POI / quest actually look like? | `forge-common` | `Read <forge-common>/world/*.json` | `forge-docs` `Create-*.md`, then the other shipped planes |
| How do I write this card ability? | `forge-card-corpus` | `unzip -p <install>/res/cardsfolder/cardsfolder.zip` + grep; `forge-docs/Card-scripting-API/` | The `Named$` escape hatch before any engine change — see [docs/ENGINE.md](docs/ENGINE.md) |
| What does `Count$` or a `Valid` predicate mean? | Engine workspace source | `grep forge-game/src/main/java/forge/game/ability/effects`, and `AbilityUtils.xCount` | `forge-upstream` on GitHub when the workspace is not bootstrapped. `AbilityFactory.md` is a curated subset and the docs explicitly decline to document `Count$` |
| Is this behaviour data-driven or engine-level? | [docs/ENGINE.md](docs/ENGINE.md) closed-set table | `Read docs/ENGINE.md` | Engine workspace source, then `forge-upstream` |
| Which upstream build am I forked from? | `OWNERSHIP.md` + the install's `build.txt` | `Read` both | `forge-upstream` releases / daily-snapshots |

## Registry

<!-- One section per reference. The yaml block is machine-read; prose below it is for
     humans. Record failed approaches and known blind spots — that's the expensive
     knowledge to rediscover. -->

## Forge offline documentation mirror

```yaml
id: forge-docs
kind: document
readonly: true
local: true
committed_path: null
url: null
volatility: frozen-snapshot
```

- **Access method:** `Read <bound path>/Adventure/*.md` and `<bound path>/Card-scripting-API/*.md`. Bound per-machine in `references.local.json`.
- **Comparison procedure:** when authoring a JSON field or a card ability, find the field named in the shipped doc before inventing one. If the doc and the observed `common/` data disagree, the data wins and the disagreement is recorded in this section.
- **Known blind spots / failed approaches:** **Confirm any coordinate, direction or ordering claim against the decompiled method before generating content from it** — `javap -p -c` against the install's `forge-gui-mobile-dev-*.jar`, which is where the Adventure classes live (the desktop jar has none). Tag the doc claim `[D]`, the bytecode claim `[B]`, and let `[B]` win. Two of the three silent in-game failures on `Archidekt_Vaults` came from trusting the prose: `Create-new-Maps.md` documents every map object type but never mentions that a tile layer must carry `spriteLayer=true` or **nothing but tiles is drawn**, and its `direction` description (*"up means the player will be teleported to the upper edge"*) is inverted relative to `EntryActor.spawn()`, where `"left"` places the player to the entry's *right*. The shipped docs also **never mention the Adventure Editor** (`adventure-editor.cmd`), so any editor behaviour is off the documented path. `Targeting.md` (4.3 KB) does not come close to covering the `Valid` predicate mini-language, and the docs explicitly decline to document `Count$` — *"There are way too many parameters that introducing all here doesn't really help. Refer to the `AbilityUtils.xCount` method in the code."* Device-path casing is inconsistent **between** shipped docs: `Card-Images.md`, `Adventure/Transfer-PC-saves-to-Android.md` and `Network-Play.md` disagree on casing and root; confirm on-device before scripting a deploy.

## Forge `common/` fallback layer

```yaml
id: forge-common
kind: dataset
readonly: true
local: true
committed_path: null
url: null
volatility: frozen-snapshot
```

- **Access method:** `Read` / `grep` under the bound path (`res/adventure/common`). Plane resolution is plane-first with `common` fallback, at **whole-file** granularity.
- **Comparison procedure:** before forking any `common/` file, diff the intended change against the stock file and check whether referencing it by path would do instead. When a fork is unavoidable, record the file and the install's `build.txt` in `OWNERSHIP.md` in the same edit.
- **Known blind spots / failed approaches:** modifying a stock tileset changes **every map in every plane** — copy into your own plane's subdirectory instead. Fallback replaces, it never merges: `Realm of Legends` ships its own `enemies.json` and therefore inherits none of common's 464 entries going forward, while still borrowing sprites from common's 493 atlases by path. Four files cannot fall back at all, because they do not exist in `common/world/` and must be shipped per-plane: `world.json`, `quests.json`, `shops.json`, `town_names_*.txt`.

## Forge card script corpus

```yaml
id: forge-card-corpus
kind: dataset
readonly: true
local: true
committed_path: null
url: null
volatility: frozen-snapshot
```

- **Access method:** `unzip -p <bound path>/cardsfolder.zip '<pattern>'`, or extract to a scratch directory outside this repo. 33,696 stock card scripts.
- **Comparison procedure:** find two or three stock cards doing the thing you want and copy their idiom before writing a novel one. For Adventure-only cards the canonical minimal template is `common/custom_cards/flame_sword.txt` — a `PayShards<N>` cost, `ActivationZone$ Command`, and the self-exile `SubAbility` idiom.
- **Known blind spots / failed approaches:** a custom card whose name collides with a real MTG card **silently resolves to the real one**. A card script with no matching edition entry is **silently skipped**. Both failures are quiet, which is why they belong in the linter rather than in a checklist.

## Forge token script corpus

```yaml
id: forge-token-corpus
kind: dataset
readonly: true
local: true
committed_path: null
url: null
volatility: frozen-snapshot
```

- **Access method:** `Read` / `grep` under the bound path (`res/tokenscripts`). 839 token scripts.
- **Comparison procedure:** resolve every token name a card creates against this set plus `custom/tokens/` before shipping the card.
- **Known blind spots / failed approaches:** none yet.

## Forge upstream repository

```yaml
id: forge-upstream
kind: upstream-repo
readonly: true
local: false
committed_path: null
url: https://github.com/Card-Forge/forge
volatility: live
```

- **Access method:** `WebFetch https://github.com/Card-Forge/forge`, `gh api`, or the engine workspace clone. Daily snapshots are published under the `daily-snapshots` release tag, whose `build.txt` is what the Android client compares against.
- **Comparison procedure:** when an upstream bump lands, diff every file listed in `OWNERSHIP.md` against its new stock version, and re-apply `engine/patches/*.patch` onto the new pin. Both are mechanical **only** because the ledger records what was forked and at which build.
- **Known blind spots / failed approaches:** snapshot cadence is daily, so `res/` churns constantly — "which upstream build am I forked from" is tracked state, not something to reconstruct later. Upstream declines new engine mechanics originating outside official cards, which is why the `Named$` escape hatch matters more here than a PR would.

<!-- Section template (copy for a new reference):

## <Display name>

```yaml
id: <kebab-slug>
kind: website | api-spec | binary | upstream-repo | dataset | document
readonly: true
local: <true if the location is a machine-local path bound via references.local.json, else false>
committed_path: <repo-relative path if the reference lives inside this repo, else null>
url: <URL if the reference is remote, else null>
volatility: live | frozen-snapshot
```

- **Access method:** <the exact command/tool to read it, e.g. "WebFetch <url>", "Read <path>", a decompile procedure>
- **Comparison procedure:** <concrete steps to check our output against it>
- **Known blind spots / failed approaches:** <evidence-standard entries, or "none yet">
-->
