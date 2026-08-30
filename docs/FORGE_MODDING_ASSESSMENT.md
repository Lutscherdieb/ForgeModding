# MTG Forge — modding accessibility assessment

**Subject:** MTG Forge `2.0.15-SNAPSHOT`, `build.txt` = `2026-08-20 18:53:10`
**Install:** `E:\Programme\MTGForge` · **User data:** `%APPDATA%\Forge` · **Cache:** `%LOCALAPPDATA%\Forge\Cache`
**Written:** 2026-08-22 · **Scope:** Adventure Mode content + custom cards, PC and Android

Every claim below is tagged with how it was established:
**[F]** verified against files in this install · **[B]** decompiled from jar bytecode · **[D]** stated in Forge's own shipped docs · **[I]** inferred, not yet tested — see §11.

---

## 1. Verdict

Adventure Mode is **substantially more moddable than it looks**, and more moddable than most games with an official editor. It is a data-driven content system: a "plane" is a folder of JSON + Tiled maps + libGDX atlases + deck files, discovered by a plain directory scan with no registry to edit, no build step, and no Java. Forge ships a GUI editor for most of it.

Structurally it is very close to the Cube Chaos `GameData/<ModName>/` model you already work in: one folder per mod, dropped in, auto-discovered.

There are exactly two real problems, and both are solvable:

1. **Plane folders must live inside the install directory**, which the installer overwrites. Custom cards do not have this problem. → §7.
2. **Forking a shared file means owning it forever.** File-level fallback is all-or-nothing, so shipping your own `enemies.json` forfeits every future upstream enemy. → §2.

### Scorecard

| Content type | File(s) | Tool | Difficulty | Needs Java? |
|---|---|---|---|---|
| Plane skeleton | folder + `config.json` + 4 world files | copy/paste | 1 | no |
| Difficulty / economy tuning | `config.json` | text editor | 1 | no |
| Card-pool restriction | `config.json` | text editor | 1 | no |
| Enemies & bosses | `world/enemies.json` | Adventure Editor | 2 | no |
| Items & equipment | `world/items.json` | Adventure Editor | 2 | no |
| Decks | `decks/**/*.dck` | Forge deck editor | 2 | no |
| Adventure-only custom cards | `custom_cards/*.txt` | text editor | 2–4 | no |
| Shops | `world/shops.json` | text editor | 2 | no |
| Points of interest | `world/points_of_interest.json` | Adventure Editor | 3 | no |
| Sprites | `.png` + `.atlas` | GIMP/Aseprite + text | 3 | no |
| Constructed custom cards + sets | `%APPDATA%\Forge\custom\` | text editor | 3 | no |
| Quests & dialogue | `world/quests.json` | Adventure Editor | 4 | no |
| Dungeon / town maps | `maps/**/*.tmx` | Tiled | 4 | no |
| Overworld / biome generation | `world/world.json` + `biomes/*.json` | Adventure Editor + GIMP | 4 | no |
| New *kinds* of item effect / quest objective | — | — | 5 | **yes** |
| New engine mechanics | — | — | 5 | **yes** |

Nothing in the first fifteen rows requires compiling anything.

---

## 2. How Forge resolves files

This is the foundation; everything else refers back to it.

### 2.1 The assets chain is not configurable **[B]**

```
GuiBase.getInterface().getAssetsDir()   →  ASSETS_DIR
ASSETS_DIR + "res/"                     →  RES_DIR
RES_DIR   + "adventure/"                →  ADVENTURE_DIR
ADVENTURE_DIR + "common/"               →  ADVENTURE_COMMON_DIR
```

`getAssetsDir()` is supplied per platform and resolves to the program directory on desktop. Every launcher script starts with `pushd %~dp0`, so `./res` is always the install root.

`forge.profile.properties` (copy `forge.profile.properties.example` to activate) can relocate **only**: `userDir`, `cacheDir`, `cardPicsDir`, `cardPicsSubDirs`, `decksDir`, `decksConstructedDir`. **There is no `resDir` or `assetsDir` key** — confirmed by reading `ForgeProfileProperties` bytecode, which parses exactly those six names. **[B]**

Consequence: user data is relocatable, `res/` is not. This is the single fact that shapes §7.

### 2.2 Plane resolution: plane-first, `common` fallback **[B][F]**

`forge.adventure.util.Config` builds a `prefix` (your plane) and a `commonPrefix` (`res/adventure/common`), and `getFile()` returns the plane's copy if present, else common's. Discovery is `new File(ADVENTURE_DIR).list(filter)` — **no manifest, no registry, no index file anywhere.** Drop a folder in, it appears in the Settings dropdown.

Evidence of how far the fallback carries you: **Shandalar is 15 files. Amonkhet is 5.** **[F]**

Selection is persisted as `SettingData.plane` under `USER_ADVENTURE_DIR`; default `"Shandalar"`. Switching planes requires a restart, and save files are per-plane. **[B][D]**

### 2.3 The fork-cost asymmetry — the most important mechanic here **[F]**

Fallback works at **whole-file** granularity, but asset *references inside* those files resolve through to `common/`. These two facts pull in opposite directions and you must design around both.

Measured on this install:

| | `common` | `Realm of Legends` | shared names |
|---|---|---|---|
| enemies | 464 | 956 | **22** |

Realm of Legends ships its own `enemies.json`, so it owns all 956 entries and inherits **none** of common's 464 going forward. There is no merge — the file replaces.

But: RoL ships **5** sprite atlases while common ships **493** enemy atlases, and RoL's entries reference paths like `sprites/enemy/humanoid/conjurer.atlas` that resolve into `common/`. **[F]**

> **Rule: any file you ship is a permanent fork of that file. Any asset *path* you reference is free.**
>
> Prefer referencing stock sprites, decks and atlases by relative path. Fork a shared JSON only when you actually need to, and record which upstream build you forked it at — that is what makes reconciling a later update mechanical instead of archaeological.

### 2.4 Canonical plane file map **[B]**

From `forge.adventure.util.Paths`, verbatim — these paths are fixed, no renaming:

```
world/enemies.json              world/shops.json
world/world.json                world/heroes.json
world/points_of_interest.json   world/items.json
world/quests.json               world/cardprices.txt
custom_cards/                   custom_card_pics/
skin/ui_skin.json               skin/equip.png
skin/unusable.png               skin/keys.atlas
sprites/items.atlas             sprites/pixelmana.atlas
sprites/map_marker.atlas        ui/color_frames.atlas
ui/arena.atlas
particle_effects/{heal,killed,kill,hide,sprint,fly,teleport,blood,sparks}.p
```

Four of these are **mandatory per-plane** because they do not exist in `common/world/` and therefore cannot fall back: **`world.json`, `quests.json`, `shops.json`, `town_names_*.txt`**. `config.json` *does* fall back to `common/config.json`. **[F]**

Beyond `Paths`, a plane may also carry `editions/` and `blockdata/blocks.txt` for entirely custom card sets — read by `AdventureOverrides` via `CardEdition$Reader` / `CardBlock$Reader`. `Shandalar Old Border` is the working example. **[B][F]**

### 2.5 Scale reference

For estimating effort against what already exists **[F]**:

| | count |
|---|---|
| `common/world/enemies.json` | 464 enemies |
| `common/world/items.json` | 200 items |
| `common/world/points_of_interest.json` | 264 POIs |
| `common/world/heroes.json` | 16 playable races |
| `common/world/biomes/*.json` | 13 biomes |
| `common/decks/**/*.dck` | 566 decks |
| `common/maps/**/*.tmx` | 390 maps |
| `common/sprites/enemy/**/*.atlas` | 493 atlases |
| `common/custom_cards/*.txt` | 68 Adventure-only cards |
| `Shandalar/world/quests.json` | 53 quests / 139 stages / 311 KB |
| `Shandalar/world/shops.json` | 276 shops |

Plane sizes: Amonkhet 5 files · Shandalar 15 · Innistrad 163 · Shandalar Old Border 1266 · Realm of Legends 1470.

---

## 3. Adventure content, type by type

### 3.1 Enemies — `world/enemies.json` **[F][D]**

Full key set from `EnemyData` **[B]**:
`name, nameOverride, sprite, deck, ai, boss, flying, randomizeDeck, copyPlayerDeck, scale, colors, teamNumber, questTags, gamesPerMatch, spawnRate, difficulty, speed, life, lifetime, equipment, bossInsult, bossIntro, nextEnemy, rewards`

Real entry, `common/world/enemies.json`:

```json
{
  "name": "Abyssal Baron",
  "sprite": "sprites/enemy/fiend/abyssalbaron.atlas",
  "deck": [ "decks/standard/demon_swamp.dck" ],
  "spawnRate": 1, "difficulty": 2, "speed": 31, "life": 30,
  "rewards": [
    { "type": "deckCard", "probability": 1, "count": 2, "addMaxCount": 5,
      "rarity": [ "rare", "Mythic Rare" ] },
    { "type": "gold", "probability": 0.3, "count": 10, "addMaxCount": 90 },
    { "type": "shards", "probability": 0.5, "count": 1, "addMaxCount": 2 }
  ],
  "colors": "B",
  "questTags": [ "Demon", "Humanoid", "Unholy", "IdentityBlack", "BiomeBlack" ]
}
```

Notes worth having:
- `deck` accepts a `.dck` **or** a generated-deck JSON (`{"template":{"count":60,"colors":["White"],"tribe":"Angel","rares":0.5}}`).
- **No `deck` at all → the enemy behaves as a treasure chest**, granting rewards with no fight. **[D]**
- `nextEnemy` + `bossIntro` + `bossInsult` give multi-phase boss chains, data-only.
- `copyPlayerDeck` gives a mirror match.
- Sprite `.atlas` must expose regions `Idle / Walk / Attack / Hit / Death` plus `Avatar` (the duel portrait); direction suffixes like `IdleRight`, `WalkLeftDown` are optional. **[D]**
- `scale` lets you use 32×32 art (`scale: 0.5`) instead of the 16×16 default.
- To make an enemy actually spawn, add its `name` to a biome's `enemies[]` array.

### 3.2 Items & equipment — `world/items.json` **[F]**

`ItemData`: `name, description, iconName, cost, equipmentSlot, effect, questItem, usableInPoi, usableOnWorldMap, commandOnUse, shardsNeeded, dialogOnUse`
Slots: `Neck, Left, Right, Body, Boots, Ability1, Ability2`

`EffectData` is a **closed set** — this is where the data-driven ceiling sits **[B]**:
`lifeModifier, changeStartCards, colorView, moveSpeed, goldModifier, cardRewardBonus, extraManaShards, startBattleWithCard, startBattleWithCardInCommandZone, startCardsInCommandZone, opponent/oppEffect, description`

The important one for card modding is `startBattleWithCardInCommandZone`, because it is the bridge from Adventure content to the card DSL:

```json
{ "name": "Flame Sword", "equipmentSlot": "Left", "cost": 6000,
  "iconName": "FlameSword",
  "effect": { "startBattleWithCardInCommandZone": [ "Flame Sword" ] } }
```

`iconName` is a region name in `sprites/items.atlas` — reuse an existing one and you need no art at all.

Items can also carry a full branching `dialogOnUse` tree (see `Sir Donovan's Amulet`, ~120 lines).

### 3.3 The enemy → equipment → item → card chain **[F]**

This is the whole custom-card wiring for Adventure, and it is worth stating as one line because it is not obvious from any single doc:

```
enemies.json  "equipment": ["Flame Sword"]
     ↓
items.json    "effect": { "startBattleWithCardInCommandZone": ["Flame Sword"] }
     ↓
custom_cards/flame_sword.txt   (a Forge card script)
```

Enemies have no `effect` key of their own; equipment is the mechanism. `Akroma`'s entry uses exactly this with `["Mox Pearl"]`.

### 3.4 Quests & dialogue — `world/quests.json` **[F][B]**

The deepest system, and the one with the best GUI support.

Quest: `id, isTemplate, name, description, offerDialog, prologue, epilogue, failureDialog, declinedDialog, rewardDescription, stages[]`
Stage: `id, name, description, objective, prerequisiteIDs, mapFlag/mapFlagValue, count1..count4, here, worldMapOK, anyPOI, allowInactivePOI, POIToken, POITags, questTags, enemyTags, enemyExcludeTags, mixedEnemies, itemNames, equipNames, deliveryItem, prologue, epilogue`

Text supports token substitution: `$(enemy_1)`, `$(poi_2)`.

**26 objective types** (closed enum, `AdventureQuestController$ObjectiveTypes`): `None, Arena, CharacterFlag, Clear, CompleteQuest, Defeat, Delivery, Escort, EventFinish, EventWin, EventWinMatches, Fetch, Find, Gather, Give, HaveReputation, HaveReputationInCurrentLocation, Hunt, MapFlag, Leave, Patrol, QuestFlag, Rescue, Siege, Travel, Use`

**21 dialog actions**: `addLife, addGold, addShards, deleteMapObject, activateMapObject, battleWithActorID, grantRewards, grantRewardsChoice, addMapReputation, removeItem, addItem, giveBlessing, setColorIdentity, advanceQuestFlag, advanceMapFlag, advanceCharacterFlag, setEffect, setQuestFlag, setMapFlag, setCharacterFlag, issueQuest, POIReference`

**Dialog conditions**: `actorID, hasBlessing, hasGold, hasShards, hasMapReputation, hasLife, colorIdentity, item, checkCharacterFlag/QuestFlag/MapFlag, getCharacterFlag/QuestFlag/MapFlag` (with `op`/`val`), `not`

That is a real quest scripting language, and it covers most designs without touching Java. Hand-authoring the nested JSON is genuinely painful — this is what the GUI editor is for.

### 3.5 Rewards — the `RewardData` schema, used everywhere **[D]**

Shared by enemies, chests, shops, dialog actions, quests and events. `type` is the only mandatory field: `gold, life, shards, item, card, union, deckCard`.

Card filters: `colors, rarity, editions, cardTypes, subTypes, superTypes, cardName, cardText` (**regex** — e.g. `"cast (an instant|a sorcery) from your hand"`), `deckNeeds`, plus `probability` / `count` / `addMaxCount` (difficulty-scaled).

### 3.6 Points of interest — `world/points_of_interest.json` **[F]**

```json
{ "name": "Aerie", "displayName": "Aerie", "type": "dungeon", "count": 1,
  "spriteAtlas": "../common/maps/tileset/buildings.atlas", "sprite": "Aerie",
  "map": "../common/maps/map/aerie/aerie_0.tmx",
  "radiusFactor": 0.8,
  "questTags": [ "Hostile", "Nest", "Dungeon", "Sidequest" ] }
```

`type` values in use: `cave` (105), `dungeon` (103), `town` (25), `capital` (6), `castle` (6), `sidebosseasy` (6), `sidebossmoderate` (9), `sidebosshard` (3). Note the `../common/...` relative paths — a plane can point at stock assets freely. Add the POI's `name` to a biome's `pointsOfInterest[]` to place it.

### 3.7 World generation — `world/world.json` + `biomes/*.json` **[F]**

A complete overworld is one 25-line file plus N biome files:

```json
{ "width": 700, "height": 700,
  "playerStartPosX": 0.5, "playerStartPosY": 0.5,
  "noiseZoomBiome": 30, "miniMapTileSize": 4, "tileSize": 16,
  "roadTileset": { "tilesetAtlas": "world/tilesets/terrain.atlas",
                   "tilesetName": "Road", "color": "ffffff" },
  "biomesSprites": "world/sprites/map_sprites.json",
  "maxRoadDistance": 1000,
  "biomesNames": [ "world/biomes/base.json", "world/biomes/white.json", ... ] }
```

A biome carries noise/distance weights, terrain bands, a `color`, an `enemies[]` roster of names, a `pointsOfInterest[]` roster, and `structures[]` driven by a **WaveFunctionCollapse** tiled model (a source PNG + a mask PNG + a colour→tile `mappingInfo`). The WFC structure work is the fiddliest thing in the whole system.

### 3.8 Decks — `decks/**/*.dck` **[F]**

Trivial INI, editable in Forge's own deck editor:

```
[metadata]
Name=Emrakul
[Main]
1 Black Lotus
4 Eldrazi Temple
2 Emrakul, the Aeons Torn
```

Adventure decks deliberately omit set pins (`|SET|[num]`), which makes them easy to hand-write. Organised under `common/decks/` as `boss/` (7), `miniboss/` (29), `standard/` (539), `rewards/` (35), `shop/` (3), `starter/` (58). A map object can also override an enemy's deck via the `deckOverride` property, with no `enemies.json` edit.

---

## 4. The toolchain

### 4.1 Adventure Editor — shipped, functional, and undocumented **[B]**

`adventure-editor.cmd` → `adventure-editor-jar-with-dependencies.jar` (31 MB, `Main-Class: forge.adventure.Main`). A plain Java Swing app (Nimbus L&F) that bundles the Forge stack so it can reuse `forge.adventure.data.*` for JSON round-tripping. **It must be run from the install root** — the launcher's `pushd %~dp0` guarantees that.

Five tabs:

| Tab | Edits |
|---|---|
| **World** | `world.json`, biomes, terrains, WFC structures + colour-mask mappings |
| **POI** | `points_of_interest.json` |
| **Items** | `items.json` (+ an `EffectData` sub-editor) |
| **Enemies** | `enemies.json` (+ atlas preview, deck file picker) |
| **Quests** | `quests.json` → stages → dialog tree → actions/conditions |

Rewards have a sub-editor reachable from enemies/items/quests/dialogs. A toolbar button launches the bundled Ray3K particle editor (`gdx-particle-editor.jar`) for `particle_effects/*.p`.

**Not covered — hand-edit these:** `.tmx` maps, `.dck` decks, `shops.json`, `heroes.json`, `config.json`, `ArenaData`, `AdventureEventData` (inn draft/sealed events).

> Worth flagging: the official `docs/Adventure/Modding.md` **never mentions this editor**. It names only Tiled and GIMP. The tool is real and shipped, but you are off the documented path when using it — see the round-trip risk in §11 (R1), which is the single highest-impact unknown in this document.

### 4.2 Tiled — maps **[D]**

Open `res/adventure/common/maps/main.tiled-project`. Hard constraints, all of which cause bad failures if violated:

- Orientation **Orthogonal**, layer format **CSV**, render order Right Down
- **Tile size must be 16×16** — "different settings can lead to very unintended side effects"
- Layer order top→bottom: `Objects`, `Walls`, `Clutter`, `Ground`; ≤6 tile layers
- **Exactly ONE object layer** — "having a second one will confuse the heck out of Forge"
- One tile layer must carry a custom **bool** property `spriteLayer` = `true` — case-sensitive, lowercase `s`, uppercase `L`. Omitting it makes Forge "bug-out pretty hard and require a restart"
- Set Tiled's Extensions Directory to `res/adventure/common/maps/extensions`, or object actions throw and crash the game
- **Never modify the stock tilesets** — copy into your own plane's subdirectory, or you change every map in every plane

Object templates live in `common/maps/obj/*.tx` (31 of them): `enemy` (properties `enemy`, `deckOverride`, `displayNameOverride`, `fleeRange`, `pursueRange`, `threatRange`, `speedModifier`, `waypoints`, `spawn.Easy/Normal/Hard/Insane`), `shop` (`shopList`, sign offsets), `inn`, `entry` (`direction`, `teleport`, `teleportObjectId` — empty `teleport` returns to the overworld), `treasure`, `portal`, `quest`, `dialog`.

### 4.3 Sprites **[F]**

libGDX `.atlas` is plain text and hand-writable:

```
abyssalbaron.png
size: 80,16
format: RGBA8888
filter: Nearest,Nearest
repeat: none
Avatar
  xy: 64, 0
  size: 16, 16
Idle
  xy: 0, 0
  size: 16, 16
```

Region names are the animation contract. This is scriptable from Python exactly the way your Cube Chaos sprite generators work.

### 4.4 The iteration loop **[D]**

Edit → relaunch `forge-adventure.cmd` → **F9 in-game console**. JSON edits and plane switches both require a restart, so the console is what keeps the loop tolerable:

```
spawn enemy <name>        # from enemies.json
give quest <id>           # from quests.json
give item <item id>       # from items.json
remove enemy <object id>  # object ids from the POI's .tmx
listPOI                   # from points_of_interest.json
reset map
resetQuests / resetMapQuests
sanitize editions
debug collision
dumpEnemyDeckList
```

Commands are **case-sensitive**. This is the direct analogue of the console-snippet habit in your Cube Chaos test loop — worth adopting the same "print a paste-ready command after every content change" discipline here.

### 4.5 Documentation ships locally **[F]**

`E:\Programme\MTGForge\docs\` is a full offline mirror of the GitHub wiki and is better than the website:

- `docs/Adventure/` — 21 files: `Modding.md`, `Tutorial-1-Create-your-First-Plane.md`, `Tutorial-2-A-New-Look.md` (22 KB, the map pipeline), `Tutorial-3-Configuration.md`, `Configure-Planes.md` (annotated `config.json`), `Create-Enemies.md`, `Create-Rewards.md`, `Create-new-Maps.md`, `Console-and-cheats.md`, `Equipments-and-Items.md` (20 KB catalogue), `Planes.md`, `Transfer-PC-saves-to-Android.md`, …
- `docs/Card-scripting-API/` — 8 files, ~68 KB: `Card-scripting-API.md`, `AbilityFactory.md` (25 KB), `Triggers.md` (17 KB), `Replacements.md`, `Statics.md`, `Costs.md`, `Targeting.md`, `Restrictions.md`
- `docs/Creating-a-custom-Card.md`, `docs/Creating-a-custom-Set.md`, `docs/File-Formats.md`

---

## 5. The card DSL

### 5.1 Shape

Line-oriented, one card per file, no build step. Only 18 line prefixes exist; five get you a working card.

```
Name:Grizzly Bears
ManaCost:1 G
Types:Creature Bear
PT:2/2
Oracle:
```

Prefixes: `Name`, `ManaCost`, `Types`, `PT`, `Loyalty`, `Colors`, `Oracle`, `Text`, `K` (keyword), `A` (ability), `T` (trigger), `R` (replacement), `S` (static), `SVar`, `AI`, `DeckHints`, `DeckNeeds`, `DeckHas`, plus `AlternateMode:` + an `ALTERNATE` separator for multi-face cards.

Ability grammar **[D]**:

```
A:<AB|SP|DB|ST>$ ApiName | Key$ Value | Key$ Value | ...
```

`AB` activated · `SP` spell · `DB` drawback/chained (never a root) · `ST` static, resolves off-stack.

The control flow is uniform and small: `A:` roots an ability, `SubAbility$ <SVarName>` chains the next, `SVar:<Name>:DB$ ...` defines it. Triggers and replacements use the identical `Execute$ <SVarName>` indirection.

```
Name:Soul Warden
ManaCost:W
Types:Creature Human Cleric
PT:1/1
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Creature.Other | TriggerZones$ Battlefield | Execute$ TrigGainLife | TriggerDescription$ Whenever another creature enters, you gain 1 life.
SVar:TrigGainLife:DB$ GainLife | Defined$ You | LifeAmount$ 1
Oracle:Whenever another creature enters, you gain 1 life.
```

Once you can read that one, you can read most of the corpus.

Stateful cards use a manual `Remember` register with explicit cleanup — and forgetting the cleanup is a real bug class:

```
SVar:DBTransform:DB$ SetState | Defined$ Self | Mode$ Transform | ConditionDefined$ Remembered | ConditionPresent$ Card.Instant,Card.Sorcery | ConditionCompare$ EQ1 | SubAbility$ DBCleanup
SVar:DBCleanup:DB$ Cleanup | ClearRemembered$ True
```

### 5.2 The corpus is the real documentation **[F]**

`res/cardsfolder/cardsfolder.zip` — **33,696 card scripts**, letter subfolders, plus `rebalanced/` and `upcoming/`. An unzipped `cardsfolder/` directory is a supported fallback (`CardStorageReader` falls back on any zip exception), so you can work with plain files.

`res/tokenscripts/` — **839 token scripts**, flat, same DSL with `ManaCost:no cost` and an explicit `Colors:`.

Forge's own tutorial says it outright: the simplest way to build an effect is to find a card that already does it and copy. With 33k worked examples, grep beats documentation.

There is an in-app validator: `forge.gui.card.CardScriptParser` (`isAbilityApiLegal`, `isCostLegal`, `isValidLegal`, `getTriggerErrors`, `getErrorRegions`), so malformed scripts get flagged rather than silently failing.

### 5.3 Where it actually gets hard

Two sub-languages, and they are where you will spend your debugging time:

1. **The `Valid` predicate mini-language.** `.` = filter, `+` = AND, `,` = OR. Examples from real cards: `Creature.Other`, `Card.Instant,Card.Sorcery`, `Remembered.powerLT1+YouCtrl`, `Creature.leastToughnessControlledByRememberedPlayer`. `Targeting.md` is only 4.3 KB and does not come close to covering it.
2. **`Count$`.** The docs decline to document it: *"There are way too many parameters that introducing all here doesn't really help. Refer to the `AbilityUtils.xCount` method in the code."*

The API list in `AbilityFactory.md` is likewise a curated subset; ground truth is `forge-game/src/main/java/forge/game/ability/effects` in the source tree.

### 5.4 Two injection points — pick by where the card must appear

**Adventure-only card → the plane's own `custom_cards/`.** Ships with the plane, one deploy path, works on both platforms, no edition file needed. 68 stock examples in `common/custom_cards/`. These use two Adventure-only extras: the cost `PayShards<N>` and `ActivationZone$ Command`, plus the near-universal self-exile idiom:

```
Name:Flame Sword
ManaCost:no cost
Types:Artifact
A:AB$ DealDamage | ActivationLimit$ 1 | Cost$ PayShards<3> | ActivationZone$ Command | ValidTgts$ Any | NumDmg$ X | SubAbility$ Eject | SpellDescription$ CARDNAME deals 3 damage to any target, or 5 damage to target tapped creature.
SVar:X:Count$Compare Y GE1.5.3
SVar:Y:Targeted$Valid Creature.tapped
SVar:Eject:DB$ ChangeZone | Defined$ Self | Origin$ Command | Destination$ Exile
Oracle:{M}{M}{M}: Flame Sword deals 3 damage to any target, or 5 damage to target tapped creature.
```

That is the canonical minimal template — copy it.

**Card that must appear in deckbuilding / constructed → `%APPDATA%\Forge\custom\`.** **[B][D]**

```
%APPDATA%\Forge\custom\cards\<letter>\<name>.txt     # letter subfolder convention carries over
%APPDATA%\Forge\custom\tokens\<name>.txt
%APPDATA%\Forge\custom\editions\<Set Name>.txt       # REQUIRED — a script alone does nothing
```

Edition file:

```
[metadata]
Code=MYSET
Name=My Set
Date=2026-01-01
Type=Custom

[cards]
7 M Master Chef
130 L Plains
```

Rarity letters `L C U R M S`. `Type=Custom` suppresses image downloads. Also set `ALLOW_CUSTOM_CARDS_IN_DECKS_CONFORMANCE=true` in `%APPDATA%\Forge\preferences\forge.preferences` for deck-legality checks.

`FModel` instantiates **four** `CardStorageReader`s — stock cards, stock tokens, custom cards, custom tokens — so user scripts use the identical loader and identical DSL as stock. No recompile. **[B]**

Two traps: a custom card whose name collides with a real MTG card silently resolves to the real one; and a card script with no edition entry is silently skipped.

**Mod-defined mechanics without recompiling:** Forge declines new engine mechanics upstream, but ships a `Named$ <Yourword>` escape hatch — tag an ability, then match it with `Activated.NamedAbility<Yourword>` in statics/triggers and query it via `Count$FromNamedAbility<name>`. Their own docs invent "Meditate" and "Paranoia" entirely in script. **[D]**

---

## 6. PC + Android

You asked what dual-platform would mean. The answer is better than expected.

### 6.1 Adventure Mode on PC *is* the Android build **[F]**

`forge-adventure.cmd` launches **`forge-gui-mobile-dev-2.0.15-SNAPSHOT-jar-with-dependencies.jar`** — not the desktop jar. Adventure on your PC is the mobile UI running on desktop against the same `res/`, from the same code.

The Adventure code lives *only* in that mobile jar; the desktop jar contains a single Adventure class. Forge's own docs confirm: *"Adventure is baked into the Android/Mobile release of Forge, and as a separate executable already provided in the Desktop release package."*

**Consequence: content parity between PC and Android is the default, not a goal.** The deltas are file paths, input method, screen size and memory — not behaviour. Your PC Adventure session is already an Android preview.

### 6.2 Android's `res/` is real files on the device **[B]**

`forge.assets.AssetsDownloader` (in the mobile jar):

- resolves `ASSETS_DIR` / `RES_DIR`, reads `res/build.txt`
- compares it against `https://github.com/Card-Forge/forge/releases/download/daily-snapshots/build.txt`
- when stale, offers **Download / Ignore / Exit** for a **~270 MB** `assets.zip` from the same release tag
- fetches via `GuiDownloadZipService.downloadAndUnzip` into `assetsDir` through `temp.zip`
- before downloading, deletes only `res/version.txt` and `res/build.txt`

So the Android app writes an ordinary unzipped `res/` tree onto device storage on first launch. Two consequences:

1. **A plane folder pushed into `res/adventure/` on the device is sufficient. No APK rebuild for content.** **[I — verify, see R2]**
2. An assets refresh **unzips over** rather than pruning, so a plane folder whose paths don't collide with stock content should survive updates. **[I]**

### 6.3 Device paths **[D]**

| | Android 11+ | Android 8–10 |
|---|---|---|
| Root | `Internal Storage/Android/obb/forge.app/Forge/` | `Internal Storage/Forge/` |
| Assets | `…/Forge/res/` | `…/Forge/res/` |
| User data | `…/Forge/data/` | `…/Forge/data/` |
| Adventure saves | `…/Forge/data/adventure/<Plane>/` | same |
| Card image cache | `…/Forge/cache/` | same |

Accessing `Android/obb` on Android 11+ needs a third-party file manager with all-files permission — the Forge docs already require this for card images, so you may have it set up. `adb push` or USB/MTP from the PC also work.

**Casing/path inconsistency in the docs, unresolved:** `docs/Card-Images.md` writes `Android/obb/forge.app/Forge/cache/`, `docs/Adventure/Transfer-PC-saves-to-Android.md` writes `android/obb/forge.app/forge/data/…`, and `docs/Network-Play.md` cites `Android/data/forge.app/files/Forge/networklogs/`. Confirm on your device before scripting a deploy. → R2.

### 6.4 The boundary, stated crisply

| | PC | Android |
|---|---|---|
| Plane folder, JSON, decks, sprites, maps | file copy | file push, **no rebuild** |
| Custom card scripts / editions | file copy | file push, **no rebuild** |
| New item `effect` key, new quest objective, new console command, engine behaviour | Java + build | **APK rebuild** (Android SDK + Maven + keystore, `docs/Development/Android-Builds.md`) |

Other dual-target costs worth budgeting: UI layouts have `_portrait` variants worth checking; large sprite/map work has a mobile memory budget; saves are per-plane and transfer both directions via the documented path.

---

## 7. Recommended working architecture

Three options, and the official recommendation is not the right one for you.

| | (a) Fork Forge, branch | (b) External mod repo + deploy | (c) `git init` in the install |
|---|---|---|---|
| Source of truth | inside a 30k-file monorepo | your own small repo | the install dir |
| Survives Forge update | yes (rebuild from source) | yes (install is disposable) | **no** |
| Iteration loop | build from source (Maven/JDK/IntelliJ) | launch installed Forge | launch installed Forge |
| Android | **still needs an APK rebuild** | `adb push`, no rebuild | no path |
| Mod is a shippable unit | no (a branch diff) | **yes (a folder)** | no |
| `git status` signal | poor (upstream churn) | perfect | terrible |

**Recommendation: (b).**

`docs/Adventure/Modding.md` recommends (a) — *"create your own git branch, and use a local repository to control all your files"* — but that optimises for *contributing to Forge*, not for *maintaining a mod*. It costs a full clone plus a Maven/JDK/IntelliJ toolchain just to see a JSON edit, buries your diff in daily upstream churn across 30k files, and critically **does not solve Android**, because building from source still means building and signing an APK.

(c) is out: the install is IzPack-managed and disposable, and you would be versioning gigabytes of stock content.

### 7.1 Shape

```
E:\Projekte\ForgeModding\
  planes\<PlaneName>\        # authored content, ships as-is
  custom\                    # global custom cards/editions → %APPDATA%\Forge\custom
  tools\                     # deploy + verify scripts
  docs\                      # this file
  OWNERSHIP.md               # which common files you forked, at which upstream build.txt
```

**PC deploy is a one-time junction**, which is the ergonomic win — it makes the install a render target while the repo stays the source of truth, and it means the Adventure Editor's install-side writes land directly in your repo with no pull-back step:

```
mklink /J "E:\Programme\MTGForge\res\adventure\<PlaneName>" "E:\Projekte\ForgeModding\planes\<PlaneName>"
```

`/J` needs no admin rights and Win32 traverses junctions transparently, so Forge, the editor and Tiled all just see a folder. Make the deploy script idempotent — check for the reparse point, recreate it if a Forge reinstall removed it.

**Android deploy** is `adb push planes/<Plane> /sdcard/Android/obb/forge.app/Forge/res/adventure/`, with MTP as the fallback. Checksum both sides rather than trusting the push.

### 7.2 Keep `OWNERSHIP.md` from day one

One row per file you forked from `common/`, with the upstream `build.txt` timestamp you forked it at. Given §2.3, this is what turns a future "upstream added 40 enemies" from archaeology into a diff. It costs nothing now and is expensive to reconstruct later.

### 7.3 The script that pays for itself

Forge's failure mode for bad content is **silent fallback, not an error** — which is exactly the class of bug your Cube Chaos rules exist to prevent. A pre-launch linter turns a 3-minute relaunch cycle into a 2-second one. Worth checking:

1. every `.json` parses
2. every `sprite` path resolves in plane **or** common, and the named region exists in the `.atlas` text
3. every `deck` path resolves, and **every card name in every `.dck` resolves** against `cardsfolder.zip` ∪ `tokenscripts/` ∪ plane `custom_cards/` ∪ common `custom_cards/` — this is the number one silent failure
4. every `equipment` name exists in the effective items list; every `iconName` exists in `items.atlas`
5. every `startBattleWithCard*` name resolves
6. divergence between each forked file and the current installed `common` version, per `OWNERSHIP.md`

---

## 8. Walls — what genuinely needs Java

Precise, so it is actionable rather than discouraging. **New instances are free; new kinds are not.**

- **`EffectData`** — item effects are a closed set of ~12 fields. A new *kind* of item effect needs engine code.
- **`ObjectiveTypes`** — 26 quest objectives, closed.
- **Reward `type`** — `gold, life, shards, item, card, union, deckCard`, closed.
- **Dialog actions/conditions** — closed enums (21 / ~14).
- **Fixed relative paths** in `Paths.class` — exact filenames and locations required, no renaming.
- **`ArenaData` and `AdventureEventData`** exist in the data layer but have no GUI — the arena and inn draft/sealed events are JSON-only.
- **Harmless quirk:** a `DEV_MODE_ENABLED`-gated hardcoded hide-list for `Amonkhet`, `Innistrad`, `Crystal_Kingdoms`. Your plane is never in it, so it always shows.
- **Upstream policy:** Forge declines new mechanics from outside official cards — but the `Named$` escape hatch (§5.4) works locally without recompiling.

---

## 9. Ecosystem

Worth knowing before investing, because it determines whether work can be upstreamed rather than maintained privately forever.

Shipped plane quality **[D]**: Shandalar *"fully functional"* · Realm of Legends and Shandalar Old Border *"99% functional"* · Innistrad *"technically alpha… receiving the most work"* · Crystal Kingdoms *"very pre-alpha"* · Amonkhet ***"very broken"***.

In one 11-day changelog window (2026-08-09 → 08-20), Adventure content was the single most active area in the project: a community modder shipped **three** Realm of Legends releases merged straight into mainline, including *"8 new dungeons + new town"*, alongside ongoing engine work on quest indicators, quest log and dungeon rendering. **[F]** Zero commits in that window touched the adventure-editor — the tool is stable while the content pipeline around it is hot.

The practical implication: because a plane is a **self-contained folder**, upstreaming is a copy and a commit, not a rebase. Keep a Forge fork purely as a publishing target if you ever want that.

---

## 10. Recommended first project

The smallest mod that exercises the entire pipeline end to end. Zero art required — every visual asset is borrowed by path, which also *proves* the fallback rule in §2.3. Spaces in plane names are safe (`Realm of Legends` ships that way).

**Files**

1. `config.json` — copy `common/config.json`, change one thing as a tell: `"playerBaseSpeed": 64` (common is 32). If you move at double speed, your config is live; if not, you are silently running common's.
2. `world/*` — copy `Shandalar/world/*` wholesale (the 4 mandatory files). Everything else falls back.
3. `custom_cards/proving_totem.txt` — modelled on `flame_sword.txt`. Use a boring API (`Pump`) deliberately, so any failure is a plumbing failure, not a DSL failure.
4. `world/items.json` — common's 200 plus one entry with `"iconName": "FlameSword"` (no atlas work) and `effect.startBattleWithCardInCommandZone: ["Proving Totem"]`.
5. `world/enemies.json` — common's 464 plus one `"Proving Dummy"`: `sprite: "sprites/enemy/fiend/abyssalbaron.atlas"` (falls back to common — proves §2.3), `life: 10`, high `spawnRate`, `"equipment": ["Proving Totem"]`.
6. `decks/standard/proving_dummy.dck` — trivial 40-card mono-red.
7. `OWNERSHIP.md` — three rows, recording that `config.json`, `items.json` and `enemies.json` were forked at `build.txt 2026-08-20 18:53:10`.

**Gates** — each proves one distinct thing; stop at the first failure.

| | Gate | Proves |
|---|---|---|
| G1 | Plane appears in the dropdown | folder discovery + `config.json` |
| G2 | World generates, movement visibly doubled | *your* config is the live one |
| G3 | F9 `spawn enemy "Proving Dummy"` works, borrowed sprite renders | `enemies.json` + asset fallback |
| G4 | `give item`, fight, totem in command zone, `PayShards` activates | `items.json` + plane-local `custom_cards/` + Adventure-only cost — **also the test for R3** |
| G5 | Enemy fields the totem too | the `equipment` → item → card chain |
| G6 | `adb push`, re-run G1–G5 on device, no APK rebuild | dual-platform — **the test for R2** |
| G7 | Delete the junction, redeploy, G1 still passes | the architecture; install confirmed disposable |

Out of scope for session one: any `.tmx` map, any new sprite atlas, any quest/dialog tree. Those are the difficulty-4 items.

---

## 11. Verify log

Claims this document could not test from the PC, ordered by impact. **The document is not "done" until the Result column is filled.**

| # | Claim | Confidence | Test | Result |
|---|---|---|---|---|
| R1 | **The Adventure Editor round-trips JSON losslessly** — an editor built from a different snapshot could silently drop unknown fields or reformat whole files. The junction design hands it write access to your repo, so a lossy round-trip would be discovered late and painfully | **Unknown — highest impact** | Open `items.json` in the editor, save with no changes, `git diff`. Do this *before* trusting it with real content | |
| R2 | Android res root is exactly `/sdcard/Android/obb/forge.app/Forge/res/`, and `adb` can write there on modern Android | High that it exists and is writable; **medium** on casing/OEM variance — the shipped docs disagree with each other (§6.3) | `adb shell ls /sdcard/Android/obb/forge.app/Forge/res/adventure` | |
| R3 | Per-plane `custom_cards/` are actually loaded, not just `common/custom_cards/` | **Medium** — a negative here would force custom cards back into the install dir and partially reopen the deploy problem | Gate G4 | |
| R4 | A custom plane folder survives the Android `assets.zip` refresh | Medium-high — the updater unzips over and prunes only `version.txt`/`build.txt` | Accept the next snapshot bump, re-check | |
| R5 | A custom plane folder survives an in-place PC upgrade | Medium — it is untracked in `Uninstaller/install.log` (which tracks 6,051 stock Adventure entries), but a clean reinstall definitely removes it | Take one update and observe | |
| R6 | Forge, the Adventure Editor and Tiled all read through a Windows junction | High but untested | 60 seconds, at G1 | |
| R7 | The Android equivalent of `%APPDATA%\Forge\custom\` is `<obb>/Forge/data/custom/` | Medium | Push one custom card + edition file, check the deck editor on device | |
| R8 | `custom_card_pics/` art is picked up per-plane on both platforms | Low / unknown | Add one image in session two | |
| R9 | `ALLOW_CUSTOM_CARDS_IN_DECKS_CONFORMANCE` is reachable from the mobile UI | Medium — it is a desktop preference | Check the mobile settings screen | |
| R10 | Daily snapshot cadence means `res/` churns constantly under you | High | Pin `build.txt` in `OWNERSHIP.md`; treat "which upstream build am I forked from" as tracked state | |
| R11 | Licensing / asset provenance if publishing (Forge's licence, MTG IP, third-party art) | n/a | Resolve before any public release, not after | |

---

## 12. Path cheat sheet

**PC**

```
E:\Programme\MTGForge\                       install root (installer overwrites this)
  forge.cmd                                  desktop Forge (desktop jar)
  forge-adventure.cmd                        Adventure   (MOBILE jar — see §6.1)
  adventure-editor.cmd                       the Swing content editor
  gdx-particle-editor.jar                    particle effects (.p)
  build.txt                                  which upstream build you are on
  docs\                                      full offline wiki mirror
  res\adventure\<Plane>\                     ← plane mods go here
  res\adventure\common\                      shared fallback layer
  res\cardsfolder\cardsfolder.zip            33,696 stock card scripts
  res\tokenscripts\                          839 token scripts

%APPDATA%\Forge\                             user data (relocatable)
  custom\cards\<letter>\<name>.txt           ← global custom cards
  custom\tokens\  custom\editions\
  preferences\forge.preferences
  decks\  quest\  gauntlet\  achievements\
  forge.log

%LOCALAPPDATA%\Forge\Cache\pics\cards\<SET>\ card images
```

**Android 11+** (Android 8–10: drop `Android/obb/forge.app/`, root at `Internal Storage/Forge/`)

```
Internal Storage/Android/obb/forge.app/Forge/
  res/adventure/<Plane>/                     ← plane mods go here
  data/                                      user data
  data/adventure/<Plane>/                    saves (transferable both ways)
  cache/                                     card images
```

---

## 13. Bottom line

For Adventure content, Forge is a **genuinely accessible modding target** — arguably a friendlier one than Cube Chaos, because the schemas are JSON with a GUI editor rather than a bespoke DSL, and because 33,696 worked card examples ship in the box. Everything you would want to build (enemies, bosses, quests, dialogue, items, shops, biomes, terrain, POIs, starting decks, custom cards, custom sets, UI skin, music) is reachable from data files alone.

The three things to internalise before starting:

1. **Reference stock assets by path; fork shared files only when you must** (§2.3). This decision compounds.
2. **The install directory is disposable** — keep the mod in its own repo and deploy into the install (§7).
3. **Silent fallback is the default failure mode**, so build the linter early (§7.3).

Suggested next step: run the first project in §10. Seven files, one session, and it converts every `[I]`-tagged claim in this document into a `[F]`.
