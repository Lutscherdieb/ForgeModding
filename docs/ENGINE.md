# ForgeModding — the engine (Java) track

What this doc promises: how a Java change to Forge gets made, built, versioned and re-applied here — and, first, how to be sure you actually need one.

The content track is the default. This one exists because a handful of content types are gated behind closed Java enums, and no amount of JSON reaches them. **New instances are free; new *kinds* are not.**

---

## 1. Do you actually need Java?

Check this table before writing a line of it. Everything on the left is data work; only the right column forces the engine track.

| You want… | Data layer? | Notes |
|---|---|---|
| A new enemy, boss, item, quest, shop, POI, deck, biome, sprite, map | **yes** | The entire content track. Nothing here needs Java. |
| A new *card mechanic* | **yes — `Named$`** | See §2. Forge's own docs invent "Meditate" and "Paranoia" entirely in script. |
| A new **kind** of item effect | no | `EffectData` is a closed set of ~12 fields. |
| A new **kind** of quest objective | no | `ObjectiveTypes`: 26, closed. |
| A new **kind** of reward | no | `gold, life, shards, item, card, union, deckCard` — closed. Compose with `union` first. |
| A new dialog action or condition | no | Closed enums, 21 and ~14. |
| A new console command, or engine behaviour | no | Engine code. |
| Arena / inn draft & sealed event tuning | **yes** | `ArenaData` and `AdventureEventData` exist in the data layer with no GUI — JSON-only, but not Java. |
| Renaming a plane file | **no, and not with Java either** | Paths are fixed in `Paths.class`; exact filenames and locations are required. |

### The rule

**Exhaust the data layer before writing Java.** An engine patch is a maintenance cost re-paid at *every* upstream snapshot — and upstream publishes daily. A data solution is free forever. A patch proposal must name the data-layer approach that was tried and why it failed.

---

## 2. The escape hatch that avoids most of this

Forge declines new engine mechanics originating outside official cards, and ships a documented escape hatch instead. Tag an ability with a word of your own, then match and count it:

```
Named$ <Yourword>                          # tag it
Activated.NamedAbility<Yourword>           # match it in statics / triggers
Count$FromNamedAbility<name>               # query it
```

This works locally with no recompile, on both platforms, through the ordinary content deploy path. Reach for it before the engine track, every time.

---

## 3. Why patches and not a fork

Forge's own modding docs recommend cloning the repo and working on a branch. That advice optimises for *contributing to Forge*, not for *maintaining a mod*:

- it buries this project's diff in daily upstream churn across ~30k files, so `git status` stops meaning anything;
- it costs a full clone plus a Maven/JDK/IntelliJ toolchain just to see a JSON edit;
- and it does not solve Android, because building from source still means building and signing an APK.

So: **the clone is a disposable workspace outside this repo, and only the patch series is versioned here.** The workspace can be deleted and re-created from `engine/PINNED.md` plus `engine/patches/` at any time.

### The workspace is deliberately not a declared reference

The four read-only references in [REFERENCES.md](../REFERENCES.md) point at the *install* — files this project reads constantly and must never write. The engine workspace is the opposite: it is mutable by design, so declaring it read-only would fight the `protect-references` hook on every single engine edit.

What protects it instead is a rule, and the rule is the one thing standing between you and an unrecoverable workspace:

> **Never commit to an upstream branch.** All work lives on the `forgemodding` branch and leaves as exported patches. `master`/`main` in the workspace stays pristine, so `git diff` against it is always exactly this project's engine change.

---

## 4. Layout

```
engine/
  PINNED.md              upstream commit + build.txt the series applies to; one entry per patch
  patches/               NNNN-<slug>.patch, git format-patch order
  workspace.local.json   (gitignored) { "workspace": "<absolute path to the Forge clone>" }
```

The clone itself never lives inside this repo. `engine/workspace/` and `engine/build/` are gitignored as a backstop in case someone puts one there anyway.

---

## 5. The workflow

```
python tools/engine_bootstrap.py    # prereq check, clone, pin, create the forgemodding branch
python tools/engine_apply.py        # reset to the pin, apply patches/*.patch in order
python tools/engine_build.py        # maven build, then copy the jars into the install
python tools/engine_export.py       # forgemodding branch -> patches/*.patch, refresh PINNED.md
```

The loop is: `apply` → edit in the workspace → commit on `forgemodding` → `build` → test in game → `export`. Only `export` writes to this repo.

### Bootstrapping (M2)

Prerequisites, none of which are installed on this machine yet:

| | Status here | Needed for |
|---|---|---|
| JDK | present — `openjdk 26.0.2.1` | building |
| Maven | **missing** | building |
| Forge clone | **missing** | everything |
| Android SDK + keystore | missing | M4 only, not now |

**Open `[I]`:** JDK 26 is what this machine has; Forge's target Java version has not been checked. Verify it against the upstream `pom.xml` before assuming the build failure you get is your fault. Record the answer here as `[F]` when you have it.

### Re-applying after an upstream snapshot

Snapshots are daily; `res/` and the source both churn. On a bump:

1. Fetch upstream, pick the new commit, update `engine/PINNED.md` and `OWNERSHIP.md`'s engine-pin row.
2. `engine_apply.py` onto the new pin. Conflicts are the real cost of this track — resolve them on the `forgemodding` branch.
3. `engine_export.py` to re-cut the series.
4. Re-run the content linter too: the same bump may have changed files listed in `OWNERSHIP.md`.

---

## 6. Platform reach — engine features are PC-only for now

This is the cost the engine track pays, and it is stated rather than discovered:

| | PC | Android |
|---|---|---|
| Plane folders, JSON, decks, sprites, maps | file copy / junction | `adb push`, **no rebuild** |
| Custom card scripts and editions | file copy | file push, **no rebuild** |
| Anything in `engine/patches/` | Maven build | **APK rebuild** — Android SDK + Maven + keystore |

Content parity between the two platforms is the default rather than a goal, because `forge-adventure.cmd` launches the *mobile* jar: Adventure on PC is the Android UI running on desktop against the same `res/`, from the same code. Engine changes break that symmetry, and until M4 lands they simply are not on the device.

---

## 7. Per-patch discipline

Every patch is recorded in [engine/PINNED.md](../engine/PINNED.md) with:

- the closed set it extends (`EffectData`, `ObjectiveTypes`, reward `type`, dialog actions/conditions, …),
- the content type it unlocks,
- the data-layer approach that was tried first and why it failed,
- and what under `planes/` or `custom/` consumes it.

**A patch that no content consumes does not ship.** An unconsumed patch is pure carrying cost: it has to be re-applied at every snapshot bump and proves nothing when it breaks.
