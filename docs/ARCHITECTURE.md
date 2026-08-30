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

`deploy.py` maintains the PC junction and the Android push. `verify.py` is the linter and this project's verify gate. `engine_*.py` bootstrap, apply, build and export the engine track.

`archidekt_sync.py` and `gen_vault.py` are the two halves of the Archidekt Vaults pipeline and the one exception to "nothing in `tools/` authors content": they generate a plane's enemies, POIs and dungeon maps from an external deck source, because hand-maintaining twenty-one enemy entries against a deck list that changes on someone else's website is a losing game. Everything else in a plane is authored by hand in the Adventure Editor, Tiled and the deck editor.

```
archidekt_sync.py <user>     gen_vault.py
  Archidekt API                 reads every decks/<user>/_roster.json
  -> decks/<user>/*.dck         -> world/enemies.json
  -> decks/<user>/_roster.json  -> world/points_of_interest.json
                                -> maps/map/vault/<user>_f*.tmx
                                -> rewrites biome pointsOfInterest only
```

The roster manifest is the seam. It records **every** deck the sync saw, kept or rejected with the reason, so "why is that deck not in my dungeon" is answered by a file rather than by re-running anything.

## Decisions & reversals

<!-- Record decisions with their why; keep reversals in place, marked as reversed
     with the reason — a retired idea that vanishes gets re-derived. -->
### Deploy by junction, not by copy

`mklink /J` from the install's `res/adventure/<Plane>` to this repo's `planes/<Plane>`. `/J` needs no admin rights and Win32 traverses junctions transparently, so Forge, the Adventure Editor and Tiled all just see a folder.

The real win is that the Adventure Editor's install-side writes land **directly in this repo**, with no pull-back step. The matching risk is that the editor gets write access to the repo before its round-trip fidelity is known — which is why R1 in the assessment's verify log is the first thing to test, ahead of authoring any real content.

### Reference stock assets by path; fork only when forced

Any file shipped here is a permanent fork of that file — fallback replaces, it never merges. Any asset *path* referenced is free and keeps resolving into `common/` forever. `Realm of Legends` is the worked example in both directions: it forked `enemies.json` and owns all 956 entries while inheriting none of common's 464 going forward, yet ships only 5 sprite atlases against common's 493 because it references the rest by path.

### Generated plane files are owned by their generator, never hand-edited

`Archidekt_Vaults` splits its files in two. Authored by hand and never touched by tooling: `config.json`, `world/world.json`, `world/biomes/*.json`, `world/shops.json`, `world/quests.json`, `world/town_names_*.txt`. Generated and overwritten on every run: `world/enemies.json`, `world/points_of_interest.json`, `maps/map/vault/*.tmx`, and everything under `decks/`.

One array crosses the line: a biome's `pointsOfInterest`. `gen_vault.py` rewrites *only* that key inside the authored biome file, because a POI that no biome names is simply never placed on the overworld and nothing in Forge says so — leaving that list to be maintained by hand is a silent-loss bug waiting for its first new dungeon.

### Every generated `.tmx` carries exactly one `spriteLayer=true` layer

A map without one renders its tiles perfectly and draws **nothing else** — no player, no enemies, no chests — because `PointOfInterestMapRenderer.render()` walks the layers and calls `stage.draw(batch)` only on the layer that is identical to `MapStage.spriteLayer`. With that field null the comparison never matches and the actor group is never drawn at all. Forge's entire complaint is one line on stderr: `Warning: No spriteLayer present in map.`

The generated floors therefore ship an **empty** `Foreground` tile layer whose only job is to carry the property. `verify.py`'s `tmx-contracts` check fails the build without it, and also enforces 16×16 tiles, exactly one object layer, and a map at least as large as `config.json`'s `screenWidth` × `screenHeight`. **[B]**

### Card rewards draw *with replacement* — distinctness is bought with disjoint filters

`CardUtil.generateCards()` loops `count` times over `filtered.get(rand.nextInt(filtered.size()))` and never removes what it drew. There is no field to change that: `getPredicateResult` is the only pool builder and both `CardPredicate` construction sites pass `shouldBeEqual = true`, so filters cannot even be negated. One `deckCard` entry asking for nine cards can therefore hand back the same card nine times — and since the `deckCard` pool is `Deck.getAllCardsInASinglePool().toFlatList()`, a Commander deck's 7–15 basic lands are that many separate entries and dominate the draw.

The data-layer answer is to stop asking one entry for nine cards. A haul is emitted as **one single-draw entry per bucket**, with buckets chosen so no card can sit in two: rarity is exclusive per printing (`rarities.contains(card.getRarity())`) and the mana-cost bands partition the curve. One draw per bucket × disjoint buckets = no duplicate is possible. Never listing `BasicLand` — its own `CardRarity`, not a Common — drops basics from the haul entirely.

`addMaxCount` is deliberately absent from those entries: it adds difficulty-scaled *extra* draws to the same entry, which would put duplicates straight back. Quantity comes from how many buckets a deck earns instead, which also means the difficulty's `rewardMaxFactor` no longer scales deck-card count.

`verify.py`'s `reward-no-duplicates` check enforces all of it, including that every `rarity` string is one `CardRarity.smartValueOf()` knows — an unrecognised name returns `Unknown` and the reward silently vanishes. **[B]**

A guaranteed-distinct draw for an arbitrary count would need the engine track: a `noDuplicates` flag on `RewardData` that makes `generateCards` draw without replacement. That is a legitimate first patch candidate — the data-layer approach above is the one that was tried, and its limit is that distinctness costs one disjoint bucket per card.

### Roamer sprites are derived from shipped content, not hardcoded

`Realm of Legends` is a plane of nothing but commanders — 956 enemies, 362 distinct sprites, one per legend. `gen_vault.py` reads its `enemies.json` and reuses the sprite it already assigned to any legend we also have; 15 of 21 roamers are cast that way. The paths it yields point into `common/`, which this plane resolves by fallback, so borrowing one copies nothing and adds no ownership row.

Below that sit two fallbacks: the commander's own creature types (`Assassin` → a rogue, `Spirit` → a ghost, `God` → a titan), then colour identity. A missing install or a renamed sprite degrades a tier rather than failing, and `verify.py`'s `sprite-resolve` check catches anything that stops existing. Hardcoding a name→sprite table here would have been a list the tree can supply.

### Floors must not collide and walls must — checked, not assumed

`MapStage` calls `loadCollision()` on **every** tile layer, so which layer a tile sits in decides nothing; only its shapes in the tileset do. A colliding tile used as decoration seals a room the linter otherwise calls perfect, and a collision-free tile used as a wall is a wall you can walk through. Both are silent.

Room floors are therefore drawn from a palette lifted out of the Background layers of the stock dungeon families they are named after — `crypt`, `grove`, `lavaforge`, `magetower` and twenty more — so every one is a tile Forge already treats as walkable ground. `verify.py`'s `tile-collision` check re-proves the invariant on every run, and `map-reachability` flood-fills from the player's landing cell to confirm every roamer, chest and staircase can actually be walked to. **[B]**

### An entry's `direction` names the side it *faces*; the player lands opposite

The shipped `Create-new-Maps.md` says *"`direction` the position where to spawn. up means the player will be teleported to the upper edge of the object rectangle."* Read literally that is backwards for the horizontal cases, and `EntryActor.spawn()` is unambiguous:

| `direction` | what the engine does | where the player ends up |
|---|---|---|
| `up` | `setPosition(x + w/2 - pw/2, y + h)` | above the entry |
| `down` | `setPosition(x + w/2 - pw/2, y - ph)` | below the entry |
| `left` | `setPosition(x + w, y + h/2 - ph/2)` | **to the right** of the entry |
| `right` | `setPosition(x - pw, y + h/2 - ph/2)` | **to the left** of the entry |

An entry at the left end of a corridor therefore needs `direction="left"`. Using `"right"` puts the player one tile further left, which at a map edge is the border wall — they arrive alive, rendered, and unable to move, with no error anywhere. `verify.py`'s `entry-spawn` check decodes the Ground layer, computes the landing cell for every entry, and fails if it is solid; it also fails a first floor with no entry whose `teleport` is empty, since that is the only way out of a dungeon. **[B]**

### A biome must *omit* `enemies`, never set it to `[]`

`"enemies": []` does not mean "no overworld enemies". It means "spawn anything in the plane".

`BiomeData.getEnemyList()` copies **every** entry in `enemies.json` into the biome's list with `spawnRate` forced to 0, and only the names in `enemies` keep their real rate. `BiomeData.getEnemy(rank)` then filters that list by `difficulty <= rank` and, when the filter comes up empty, falls back to `Aggregates.random` over the **whole** list — `spawnRate` is not consulted on that path. Worse, even the weighted path returns the first candidate when every weight is 0, because `r = 0` and the loop's test is `r > 0`.

So `spawnRate: 0` is not a way to keep an enemy off the overworld. Omitting the key entirely is: the field stays null, `getEnemyList()` returns an empty list, `Aggregates.random` returns null for an empty list, and `WorldStage.spawn(null)` returns false without spawning. Enforced by `verify.py`'s `biome-enemy-list` check. **[B]**

### One enemy entry per deck, not one enemy with `deckOverride`

Tiled's stock `enemy.tx` template exposes a `deckOverride` property, which looks like the way to point twenty-one map objects at twenty-one decks while defining a single enemy. It is not.

`MapStage` handles the property by calling `EnemySprite.overrideDeck(path)`, which assigns to `this.data.deck` — and `data` is the object handed back by `WorldData.getEnemy(name)`, which returns the shared instance out of a `static` array loaded once per process. Nothing copies it. So N map objects sharing one enemy name all end up on whichever override was applied last, silently, for the rest of the session; and the mutated entry stays mutated for overworld encounters with that enemy too.

Stock content never puts more than one `deckOverride` on one name in one map, so the collision is untested upstream. `verify.py`'s `map-enemy-resolve` check now fails the build on it rather than leaving it as a warning in prose. **[B]**

### The engine track ships patches, not a fork

Forge's own modding docs recommend forking the repo and working on a branch. That optimises for *contributing to Forge*, not for *maintaining a mod*: it buries your diff in daily upstream churn across 30k files, costs a full clone plus a Maven/JDK/IntelliJ toolchain just to see a JSON edit, and does not solve Android either, because building from source still means building and signing an APK.

So the clone stays outside the repo as a disposable workspace, and only the patch series is versioned. `git status` here shows this project's changes and nothing else.

### Engine features are PC-only for now — stated, not silent

Content reaches Android with no APK rebuild, because the Android client unzips an ordinary `res/` tree onto device storage. Engine changes do not: they need the Android SDK, Maven and a keystore. Rather than pretend the two tracks have the same reach, the split is documented and the APK pipeline is a declared milestone.

Worth knowing about the platform boundary: `forge-adventure.cmd` launches the **mobile** jar, not the desktop one. Adventure on PC is the Android UI running on desktop against the same `res/`, from the same code — so content parity between PC and Android is the default rather than a goal, and a PC Adventure session is already an Android preview.
