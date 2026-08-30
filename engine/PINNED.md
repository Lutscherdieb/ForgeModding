# Engine pin & patch series

The upstream commit `engine/patches/*.patch` applies to, and one entry per patch. Kept in the same edit as any change under `engine/`. The workflow that reads and writes this file is in [docs/ENGINE.md](../docs/ENGINE.md).

## Pin

| | |
|---|---|
| Upstream | `https://github.com/Card-Forge/forge` |
| Commit | *not yet pinned — run `python tools/engine_bootstrap.py`* |
| Tag / snapshot | *not yet pinned* |
| `build.txt` at pin | *not yet pinned* |
| Workspace branch | `forgemodding` |
| Pinned on | — |

The workspace clone lives outside this repo, at the path bound in gitignored `engine/workspace.local.json`.

## Patches

None yet.

| # | Patch | Closed set extended | Content type unlocked | Consumed by |
|---|---|---|---|---|
| *(none)* | | | | |

<!-- Entry template — copy the whole block for a new patch:

### 0001-<slug>

- **Closed set extended:** `ObjectiveTypes` (26 values, closed)
- **Unlocks:** <the content type that was impossible without it>
- **Data-layer approach tried first:** <what was attempted> — failed because <reason>
- **Consumed by:** `planes/<Plane>/world/quests.json` <the content that actually uses it>
- **Files touched:** <upstream paths, so a conflict on the next bump is predictable>
- **Re-apply notes:** <anything that made this conflict last time>
-->

## Re-apply log

One line per upstream bump, so the true cost of this track is visible rather than felt.

| Date | From pin | To pin | Conflicts | Notes |
|---|---|---|---|---|
| *(none)* | | | | |
