# ForgeModding

Author and maintain MTG Forge Adventure Mode content — and the engine patches some of it needs — as a standalone, deployable mod repo.

## Status

**One plane built and playable; three engine contracts learned the hard way.** `planes/Archidekt_Vaults` is 21 roamers across a 3-floor vault, every one a real Commander deck pulled from Archidekt. The first launch found two silent failures — a map with no `spriteLayer` draws no player or enemies at all, and a biome with `"enemies": []` spawns *everything* — both now fixed, documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and enforced by `verify.py`. The vault now themes each room from its commander's creature type, casts 15 of 21 roamers with the sprite `Realm of Legends` already uses for that legend, varies patrol routes and speeds, scales decoration, chests and side loot with deck score, and hands back a duplicate-free slice of the beaten deck. Commander mode is confirmed in play (2026-08-31): a new save on this plane hands the player their commander and runs normal Commander matches, and `verify.py` now fails a plane that ships `[Commander]` decks without the config to run them. The engine track is empty.

Milestone order is in [PROJECT.md](PROJECT.md)'s direction notes — the content pipeline is proven end to end before any Java is written.

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

**Archidekt Vaults — regenerate the plane from Archidekt:**

```
python tools/archidekt_sync.py Lutscherdieb   # decks + roster manifest
python tools/gen_vault.py                     # enemies, POIs, dungeon maps
python tools/verify.py > verify-report.txt
```

Add more users by naming them: `python tools/archidekt_sync.py Lutscherdieb SomeoneElse` — each gets
their own vault dungeon on the same overworld. Only **public** decks are visible, and only ones that are
exactly 100 cards with a commander are kept; `planes/Archidekt_Vaults/decks/<user>/_roster.json` lists
every rejected deck with the reason, so a deck that vanished from the dungeon is explained by a file
rather than by guesswork. Fixing a deck on Archidekt and re-running the two scripts is the whole loop.

Once in game (F9, commands are case-sensitive, quote arguments with spaces):

```
listPOI                                       # both vault POIs should be listed
spawn enemy "Kess - Wheel"                    # deepest roamer, in the overworld
give shards 50
```

`spawn enemy` takes the `nameOverride` as seen in game — the Archidekt deck name — and works only on
the overworld, not inside a POI map.

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
| `tools/` | Deploy, verify, the Archidekt Vaults generators (`archidekt_sync.py`, `gen_vault.py`), and the engine bootstrap / apply / build / export scripts. |
| `.archidekt-cache/` | Raw Archidekt deck JSON, gitignored. Re-downloadable; `--offline` reruns the pipeline from it alone. |
| `docs/` | [ARCHITECTURE.md](docs/ARCHITECTURE.md), [ENGINE.md](docs/ENGINE.md), and the founding [assessment](docs/FORGE_MODDING_ASSESSMENT.md). |
| `OWNERSHIP.md` | What this repo has forked and from where — `common/` files with their upstream `build.txt`, plus the engine pin. |
| `verify-report.txt` | Generated evidence from the last verify run (gitignored). |

More: [PROJECT.md](PROJECT.md) (goals, quality bars, doc contract) · [REFERENCES.md](REFERENCES.md) (declared ground truths).

<!-- BASE:readme-footer:v1 START -->
---
<sub>Built on [ClaudeBase](https://github.com/Lutscherdieb/ClaudeBase): the workflow machinery (setup, audits, doc gates, sync/harvest loop) arrives via the `base` Claude Code plugin and updates with it.</sub>
<!-- BASE:END -->
