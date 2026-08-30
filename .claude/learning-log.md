# ForgeModding — learning log

Append-only harvest index. **The log is never a rule's home** — the rule itself is written into its owning doc/skill/hook (see CLAUDE.md's write-back task); each entry here just records that it happened, so `/base:promote` can find generic lessons and carry them to ClaudeBase. Every written-back lesson gets its entry **in the same edit** (the `check-lesson-tagging` hook nudges when one is missing its tags).

Entry statuses: `candidate` → `promoted-pr` (PR opened, add the URL) → `merged` | `rejected`. A `scope: generic` candidate with 2+ `applications:` dates is promotion-ready.

The entry shape (copy it, replacing every `<...>` — the angle brackets are what keep
this example from being scanned as a real candidate by `/base:promote`):

```
## <YYYY-MM-DD> — <short-imperative-slug>
- scope: <generic | project>
- status: <candidate>
- rule: <ONE imperative sentence — the rule as written into its home>
- home: <path#section where the rule now lives>
- evidence: <file:line / exact error text / N — the demoted story>
- applications: <date>[, <date>...]
```

## 2026-08-30 — scaffold-enabledplugins-as-record
- scope: generic
- status: candidate
- rule: When scaffolding a Sub's `.claude/settings.json`, write `enabledPlugins` as a record (`{"<plugin>@<marketplace>": true}`), never as an array of names — and after scaffolding, parse the file and assert `enabledPlugins` is an object, because Claude Code rejects the whole settings file silently apart from one banner.
- home: `.claude/settings.json` (fixed here); the real home is ClaudeBase's scaffold template — this project has no local owner for it, which is itself the Base gap.
- evidence: Claude Code banner "`.claude\settings.json` expected record but received array and is not in effect"; the array form arrived in commit fe9e622 "Scaffold ForgeModding from ClaudeBase 0.0.3"; the user's own `~/.claude/settings.json` already used the correct record form, so the seed disagreed with the format Base itself installs. Consequence: `base@claudebase` was not enabled from the project settings for the life of the repo until noticed by eye.
- applications: 2026-08-30

## 2026-08-30 — one-enemy-entry-per-deck
- scope: project
- status: candidate
- rule: Give every enemy deck its own `enemies.json` entry; never place two map objects with the same `enemy` name and different `deckOverride` values, and let `verify.py`'s `map-enemy-resolve` check prove it.
- home: docs/ARCHITECTURE.md#one-enemy-entry-per-deck-not-one-enemy-with-deckoverride, enforced by tools/verify.py `check_map_enemies`
- evidence: [B] `MapStage` calls `EnemySprite.overrideDeck(path)`, which assigns `this.data.deck` on the object returned by `WorldData.getEnemy(name)`; that method returns the shared instance out of the `static allEnemies` array loaded once per process, and nothing copies it. N objects on one name therefore collapse onto the last override applied, session-wide. Stock content never exercises it: 21 tmx files use `deckOverride` and none puts two values on one enemy name in one map.
- applications: 2026-08-30

## 2026-08-30 — ledger-checks-must-ignore-their-own-template
- scope: generic
- status: candidate
- rule: When a check asserts "path X is recorded in doc Y", strip comment blocks and match only inside real table rows — never a bare substring search over the whole document, because the row template's worked example silently satisfies the check for exactly the case it was written to catch.
- home: tools/verify.py `check_ownership`
- evidence: `OWNERSHIP.md`'s row template comment uses `` `world/enemies.json` `` as its example. The plane genuinely forked that file; the substring search matched the template and reported "every fork is recorded". Two of three real forks were caught, the third — the most consequential one, forfeiting all 464 of common's enemies — was not. Fixed by `re.sub(r"<!--.*?-->", "", text, flags=re.S)` plus keeping only lines starting with `|`.
- applications: 2026-08-30

## 2026-08-30 — lint-only-what-the-project-owns
- scope: generic
- status: candidate
- rule: A linter check that reads through a read-only fallback/reference layer must report PASS-not-linted when the file came from that layer, never FAIL on its contents — and say which origin it used, so the skip is visible rather than assumed.
- home: tools/verify.py `check_items`, `check_battle_cards` (origin guard); the pattern already existed in `check_poi_wiring`
- evidence: with no plane-local `items.json`, the linter fell back to `common/world/items.json` and emitted 21 FAILs about stock Forge items (`'Mantle of Denial' iconName ... not a region`, `'Battle Standard' ... references 'r_1_1_goblin'`) — defects in a declared read-only reference that this repo may not edit. 21 of 24 total FAILs were noise about someone else's files, which is how a verify gate becomes something people stop reading.
- applications: 2026-08-30

## 2026-08-30 — archidekt-gate-and-owner-filter
- scope: project
- status: candidate
- rule: Filter Archidekt deck listings with `?ownerUsername=` and assert every returned deck's `owner.username` matches; compute a deck's maindeck by excluding `includedInDeck: false` categories **plus** the category named `Sideboard`, and never by name-matching token categories.
- home: tools/archidekt_sync.py module docstring + `fetch_deck_list`, `split_deck`
- evidence: `?owner=<name>` returns HTTP 200 with the global recent-decks feed — measured: 60 results, 0 owned by the requested user — so a wrong parameter name imports strangers' decks without erroring. On 37 real decks the gate passes 2 when only non-included categories are dropped, 21 when `Sideboard` is added, and mis-drops legal decks when `Tokens` is excluded by name (Delney falls 100 -> 86). `deck.edhBracket` was null on 14 of the 21 legal decks, which is why the power score is reconstructed from per-card `gameChanger`/`tutor`/`extraTurns`/`massLandDenial`/combo flags instead.
- applications: 2026-08-30

## 2026-08-30 — every-tmx-needs-a-spritelayer
- scope: project
- status: candidate
- rule: Give every authored or generated `.tmx` exactly one tile layer carrying `<property name="spriteLayer" type="bool" value="true"/>`, and prove it with `verify.py`'s `tmx-contracts` check before launching — a map without one is not "slightly wrong", it is unplayable.
- home: docs/ARCHITECTURE.md#every-generated-tmx-carries-exactly-one-spritelayertrue-layer, generated by tools/gen_vault.py, enforced by tools/verify.py `check_tmx_contracts`
- evidence: [B] `PointOfInterestMapRenderer.render()` iterates `map.getLayers()`, calls `renderMapLayer(layer)`, then `if (layer == stage.getSpriteLayer()) stage.draw(batch)`. With `MapStage.spriteLayer` null the identity test never matches and the actor group is never drawn. Observed in game: the vault rendered its tiles correctly with no player, no enemies and no chests, and the player appeared stuck. Forge's only diagnostic is `System.err`: "Warning: No spriteLayer present in map.". Negative-tested: stripping the property from one floor makes the new check emit `0 layer(s) carry spriteLayer=true`.
- applications: 2026-08-30

## 2026-08-30 — biome-enemies-key-must-be-absent
- scope: project
- status: candidate
- rule: To keep enemies off a plane's overworld, OMIT the biome's `enemies` key entirely — never `"enemies": []`, and never rely on `spawnRate: 0`, which does not prevent spawning at all.
- home: docs/ARCHITECTURE.md#a-biome-must-omit-enemies-never-set-it-to-, enforced by tools/verify.py `check_biome_enemies`
- evidence: [B] `BiomeData.getEnemyList()` adds `new EnemyData(e)` with `spawnRate = 0` for EVERY enemy in `enemies.json`, regardless of the biome's own list. `getEnemy(rank)` filters by `difficulty <= rank` and on an empty filter returns `Aggregates.random(enemyList)` — ignoring spawnRate; and its weighted branch returns the first candidate when the weights total 0, because `r = total * rand()` is 0 and the test is `r > 0`. Confirmed in play: with `"enemies": []` and all 21 roamers at `spawnRate: 0`, the user's own Ramses deck attacked them on the overworld. The absent-key path is safe end to end: `enemies == null` -> `getEnemyList()` returns empty -> `Aggregates.random` returns null for a 0-size List -> `WorldStage.spawn(null)` returns false.
- applications: 2026-08-30

## 2026-08-30 — entry-direction-is-the-facing-not-the-landing
- scope: project
- status: candidate
- rule: Set a map `entry`'s `direction` to the side the entry FACES, not the side the player should land on — `left` puts the player to its right and `right` puts the player to its left — and let `verify.py`'s `entry-spawn` check decode the Ground layer and prove the landing cell is open before launching.
- home: docs/ARCHITECTURE.md#an-entrys-direction-names-the-side-it-faces-the-player-lands-opposite, generated by tools/gen_vault.py, enforced by tools/verify.py `check_entry_spawns`
- evidence: [D] the shipped `Create-new-Maps.md` says "direction the position where to spawn. up means the player will be teleported to the upper edge of the object rectangle", which reads as the opposite for the horizontal cases. [B] `EntryActor.spawn()`: `"left" -> setPosition(x + w, ...)`, `"right" -> setPosition(x - playerWidth, ...)`. Observed in game: the corridor-left entry at col 1 with `direction="right"` put the player at col 0, the border wall — rendered but immobile, visible only as a sliver at the screen edge. Negative-tested: the new check flagged all 5 entries across 3 floors ("spawns the player into a solid tile at (0,10)") before the fix and passes after.
- applications: 2026-08-30

## 2026-08-30 — prefer-the-bytecode-over-the-shipped-doc
- scope: project
- status: candidate
- rule: When a shipped Forge doc describes a coordinate, direction or ordering, confirm it against the decompiled method before generating content from it — tag the doc claim `[D]` and the bytecode claim `[B]`, and let `[B]` win when they disagree.
- home: REFERENCES.md (forge-docs known blind spots)
- evidence: two of the three in-game failures on this plane came from trusting prose over bytecode. `Create-new-Maps.md` documents the object types but never mentions that a tile layer must carry `spriteLayer=true` or nothing but tiles is drawn, and its `direction` description is inverted relative to `EntryActor.spawn()`. Both failures are silent in game and both were found by decompiling with `javap -p -c` against the install's `forge-gui-mobile-dev-*.jar`.
- applications: 2026-08-30

## 2026-08-31 — floors-must-not-collide-walls-must
- scope: project
- status: candidate
- rule: Before using any tile id as a floor or a wall, check its collision shapes in the tileset — `MapStage.loadCollision()` runs on EVERY tile layer, so the layer a tile sits in decides nothing — and keep `verify.py`'s `tile-collision` and `map-reachability` checks green rather than eyeballing the map.
- home: docs/ARCHITECTURE.md#floors-must-not-collide-and-walls-must-checked-not-assumed, enforced by tools/verify.py `check_tile_collision` and `check_reachability`
- evidence: [B] `loadCollision(TiledMapTileLayer)` is called for every layer instance in the map, not for a named one; collision comes from `<tile id=N><objectgroup>` in main.tsx. gid 2374 carries shapes (usable wall), gid 2430 and the 24 themed floor tiles do not. Negative-tested: swapping one Ground tile to a collision-free gid and sealing one chamber doorway produced `Ground layer uses gid 2382 which has no collision` plus four unreachable-object failures; both checks pass on the generated maps.
- applications: 2026-08-31

## 2026-08-31 — derive-lookup-tables-from-shipped-content
- scope: generic
- status: candidate
- rule: When a mapping can be read out of content the project already depends on, derive it at run time and degrade to a computed fallback if the source is absent — never hardcode the table into the tool.
- home: tools/gen_vault.py `legend_sprites()` / `pick_sprite()`
- evidence: the shipped `Realm of Legends` plane assigns a sprite to each of 956 legendary creatures. Reading its `enemies.json` cast 15 of 21 commanders correctly with no table to maintain; the remaining 6 fall through to creature-type rules and then to colour identity. A hardcoded name->sprite list would have been 15 rows to re-check at every upstream snapshot, and would have silently gone stale rather than degrading.
- applications: 2026-08-31

## 2026-08-31 — card-rewards-need-disjoint-single-draw-buckets
- scope: project
- status: candidate
- rule: Never ask one card reward for more than one card when the cards must be distinct — emit one `count: 1` entry per bucket with mutually exclusive `rarity` + `manaCosts` filters, omit `addMaxCount`, and keep `verify.py`'s `reward-no-duplicates` check green; leaving `BasicLand` out of the rarity list is also the only way to keep basic lands out of a deck haul.
- home: docs/ARCHITECTURE.md#card-rewards-draw-with-replacement--distinctness-is-bought-with-disjoint-filters, generated by tools/gen_vault.py `deck_card_haul`, enforced by tools/verify.py `check_reward_duplicates`
- evidence: [B] `CardUtil.generateCards()` is `for (i < count) out.add(filtered.get(rand.nextInt(filtered.size())))` with no removal, and `getPredicateResult` is its only pool builder; both `CardPredicate` constructor sites pass `shouldBeEqual = true`, so filters cannot be negated either. The `deckCard` pool is `Deck.getAllCardsInASinglePool().toFlatList()`, so 7-15 basics are 7-15 pool entries. Measured over the 21 real decks, the rarity x cmc grid leaves 8 of 10 used buckets never empty (Common/mid empty 5/21, Mythic/lo 3/21; Common/hi and Uncommon/hi were dropped at 17/21 and 8/21). An empty bucket costs one card, never a duplicate. Negative-tested: a count-5 entry, two overlapping buckets and a bogus rarity each produced their own FAIL.
- applications: 2026-08-31

## 2026-08-31 — commander-plane-config-recipe
- scope: project
- status: candidate
- rule: To make a plane run Commander duels, ship its own `config.json` with `minDeckSize: 98`, `chaosDeckFormat: "Commander"`, and `commanderDecks` on EVERY difficulty and no other starter-deck map — then let `verify.py`'s `commander-mode-config` check prove it, because a plane that ships `[Commander]` decks without this runs `GameType.Adventure` and ignores every commander silently.
- home: docs/ARCHITECTURE.md#commander-mode-is-a-plane-config-recipe-and-it-works, enforced by tools/verify.py `check_commander_mode_config`
- evidence: [F] confirmed in play 2026-08-31 - a new save on `Archidekt_Vaults` gives the player their commander and plays normal Commander matches. [B] `DuelScene` picks `GameType.Commander` only when `AdventurePlayer.isCommanderMode()`, true for the Commander/CommanderPrecon modes or `Chaos` with `chaosDeckFormat == "Commander"`; otherwise `DeckFormat.Adventure.hasCommander()` is false. The enemy needs no second setting: `DuelScene` builds one `EnumSet` and passes the same one to `RegisteredPlayer.forVariants` for both sides - confirmed in play the same day, a vault roamer cast its own commander. Negative-tested: dropping `commanderDecks` from one difficulty, `chaosDeckFormat`, and `minDeckSize` each produced its own FAIL.
- applications: 2026-08-31
