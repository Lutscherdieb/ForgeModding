# ForgeModding — architecture

## Overview

ForgeModding is an **external mod repo that deploys into a disposable install**. The Forge install directory is IzPack-managed and gets overwritten by its own installer, and `res/` is the one path Forge refuses to relocate — `forge.profile.properties` parses exactly six keys (`userDir`, `cacheDir`, `cardPicsDir`, `cardPicsSubDirs`, `decksDir`, `decksConstructedDir`) and none of them is `resDir`. So the install cannot be the source of truth, and this repo is.

Two tracks run in parallel, with deliberately different economics:

| | Content track | Engine track |
|---|---|---|
| Artifact | a plane folder, shipped as-is | a `git format-patch` series |
| Build step | none | Maven, against a pinned upstream commit |
| Reaches Android | `adb push`, **no APK rebuild** | needs an APK rebuild — deferred milestone |
| Cost per upstream snapshot | diff the files named in `OWNERSHIP.md` | re-apply every patch onto the new pin |
| The default? | **yes** | only when the data layer genuinely cannot express it |

The asymmetry in that last row is the whole design. Content is nearly free to carry forward; an engine patch is a maintenance cost re-paid at every snapshot. [ENGINE.md](ENGINE.md) covers what actually forces the engine track.

## Components

### `planes/<PlaneName>/`

One folder per plane, matching Forge's own layout. Discovery is a plain directory scan of `res/adventure/` — no manifest, no registry, no index file — so a deployed folder simply appears in the Settings dropdown. Plane names with spaces are safe; `Realm of Legends` ships that way.

Resolution is plane-first with `common/` fallback at whole-file granularity, but asset *references inside* those files resolve through to `common/`. Those two facts pull in opposite directions, and the layout is designed around both — see the fork-cost decision below.

### `custom/`

Global custom cards, tokens and editions, deployed to `%APPDATA%\Forge\custom\`. This is the *second* of two injection points, and the one to avoid unless needed: a card only has to live here if it must appear in constructed deckbuilding. An Adventure-only card belongs in the plane's own `custom_cards/`, where it ships with the plane, needs no edition file, and works on both platforms through a single deploy path.

An edition file is **mandatory** on the global path — a card script without one is silently skipped.

### `engine/`

`patches/` holds the Java diff; `PINNED.md` records the upstream commit it applies to. The Forge clone lives outside this repo, at a machine-local path in gitignored `engine/workspace.local.json`. See [ENGINE.md](ENGINE.md).

### `tools/`

`deploy.py` maintains the PC junction and the Android push. `verify.py` is the linter and this project's verify gate. `engine_*.py` bootstrap, apply, build and export the engine track. Nothing in `tools/` authors content — authoring is the Adventure Editor's, Tiled's and the deck editor's job.

## Decisions & reversals

<!-- Record decisions with their why; keep reversals in place, marked as reversed
     with the reason — a retired idea that vanishes gets re-derived. -->
### Deploy by junction, not by copy

`mklink /J` from the install's `res/adventure/<Plane>` to this repo's `planes/<Plane>`. `/J` needs no admin rights and Win32 traverses junctions transparently, so Forge, the Adventure Editor and Tiled all just see a folder.

The real win is that the Adventure Editor's install-side writes land **directly in this repo**, with no pull-back step. The matching risk is that the editor gets write access to the repo before its round-trip fidelity is known — which is why R1 in the assessment's verify log is the first thing to test, ahead of authoring any real content.

### Reference stock assets by path; fork only when forced

Any file shipped here is a permanent fork of that file — fallback replaces, it never merges. Any asset *path* referenced is free and keeps resolving into `common/` forever. `Realm of Legends` is the worked example in both directions: it forked `enemies.json` and owns all 956 entries while inheriting none of common's 464 going forward, yet ships only 5 sprite atlases against common's 493 because it references the rest by path.

### The engine track ships patches, not a fork

Forge's own modding docs recommend forking the repo and working on a branch. That optimises for *contributing to Forge*, not for *maintaining a mod*: it buries your diff in daily upstream churn across 30k files, costs a full clone plus a Maven/JDK/IntelliJ toolchain just to see a JSON edit, and does not solve Android either, because building from source still means building and signing an APK.

So the clone stays outside the repo as a disposable workspace, and only the patch series is versioned. `git status` here shows this project's changes and nothing else.

### Engine features are PC-only for now — stated, not silent

Content reaches Android with no APK rebuild, because the Android client unzips an ordinary `res/` tree onto device storage. Engine changes do not: they need the Android SDK, Maven and a keystore. Rather than pretend the two tracks have the same reach, the split is documented and the APK pipeline is a declared milestone.

Worth knowing about the platform boundary: `forge-adventure.cmd` launches the **mobile** jar, not the desktop one. Adventure on PC is the Android UI running on desktop against the same `res/`, from the same code — so content parity between PC and Android is the default rather than a goal, and a PC Adventure session is already an Android preview.
