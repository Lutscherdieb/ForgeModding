# ForgeModding

Author and maintain MTG Forge Adventure Mode content — and the engine patches some of it needs — as a standalone, deployable mod repo.

## Status

**Newly scaffolded — nothing built yet.** Both tracks are empty: no plane authored, no engine patch written. Milestone order is in [PROJECT.md](PROJECT.md)'s direction notes — the content pipeline is proven end to end before any Java is written.

Dormant on this machine: `mvn` not installed and no Forge workspace clone (engine track blocked), `adb` not installed (Android deploy blocked, MTP is the fallback). `tools/verify.py` names each of these on every run rather than skipping them quietly.

## What this is

ForgeModding is the source of truth for MTG Forge Adventure Mode content: planes (enemies, items, quests, points of interest, decks, sprites, maps), Adventure-only and constructed custom cards, and the tooling that deploys and validates them. The Forge install is treated as a disposable render target — content is deployed into it by junction on PC and by push on Android, never authored inside it.

A second, smaller track carries Java engine patches as a `git format-patch` series against a pinned upstream commit, for the content types Forge's closed data enums genuinely cannot express (new *kinds* of item effect, quest objective, reward, or dialog action). Everything the data layer can reach stays in the data layer; the engine track is the exception, not the default.

## Run & verify

**Content track — there is no build step.** Deploy once, then edit in place:

```
tools/deploy.cmd                    # idempotent: creates or repairs the junction into the Forge install
```

It runs `mklink /J "<install>\res\adventure\<Plane>" "<repo>\planes\<Plane>"`. `/J` needs no admin
rights, and Forge, the Adventure Editor and Tiled all traverse it transparently — the install becomes a
render target while this repo stays the source of truth. A Forge reinstall removes the junction; re-run the
script to restore it.

Then launch and iterate:

```
<install>\forge-adventure.cmd      # F9 opens the in-game console — commands are case-sensitive
```

JSON edits and plane switches both require a relaunch, so every content change should end with a
paste-ready console command (`spawn enemy <name>`, `give item <id>`, `give quest <id>`, `listPOI`).

**Engine track — dormant until bootstrapped** (needs Maven and a workspace clone; see
[docs/ENGINE.md](docs/ENGINE.md)):

```
python tools/engine_bootstrap.py    # check prereqs, clone Forge outside this repo, pin the commit
python tools/engine_apply.py        # apply engine/patches/*.patch onto the pin
python tools/engine_build.py        # Maven build, then install the jars
python tools/engine_export.py       # workspace branch -> engine/patches/*.patch
```

Verify a change with: `python tools/verify.py > verify-report.txt`

## Layout

| Path | What it is |
|---|---|
| `planes/<PlaneName>/` | Authored plane content. Deployed by junction on PC, `adb push` on Android. |
| `custom/` | Global custom cards, tokens and editions → `%APPDATA%\Forge\custom\`. Only needed for cards that must appear in constructed deckbuilding; Adventure-only cards live in the plane's own `custom_cards/`. |
| `engine/patches/` | The Java engine diff, as a `git format-patch` series. The Forge clone itself lives **outside** this repo. |
| `engine/PINNED.md` | Which upstream commit and `build.txt` the series applies to, and what each patch unlocks. |
| `tools/` | Deploy, verify, and the engine bootstrap / apply / build / export scripts. |
| `docs/` | [ARCHITECTURE.md](docs/ARCHITECTURE.md), [ENGINE.md](docs/ENGINE.md), and the founding [assessment](docs/FORGE_MODDING_ASSESSMENT.md). |
| `OWNERSHIP.md` | What this repo has forked and from where — `common/` files with their upstream `build.txt`, plus the engine pin. |
| `verify-report.txt` | Generated evidence from the last verify run (gitignored). |

More: [PROJECT.md](PROJECT.md) (goals, quality bars, doc contract) · [REFERENCES.md](REFERENCES.md) (declared ground truths).

<!-- BASE:readme-footer:v1 START -->
---
<sub>Built on [ClaudeBase](https://github.com/Lutscherdieb/ClaudeBase): the workflow machinery (setup, audits, doc gates, sync/harvest loop) arrives via the `base` Claude Code plugin and updates with it.</sub>
<!-- BASE:END -->
