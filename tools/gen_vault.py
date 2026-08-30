# -*- coding: utf-8 -*-
"""Generate the Archidekt Vaults plane's enemies, POIs and dungeon maps.

WHAT THIS IS: the back half of the Archidekt Vaults pipeline. It reads the
roster manifests written by tools/archidekt_sync.py and generates, for each
Archidekt user, one multi-floor vault dungeon in which every legal Commander
deck appears exactly once as a patrolling roamer guarding its own treasure.

    python tools/archidekt_sync.py Lutscherdieb   # first
    python tools/gen_vault.py                     # then this

GENERATED, NEVER HAND-EDITED - rerunning overwrites all of these:
    planes/<plane>/world/enemies.json
    planes/<plane>/world/points_of_interest.json
    planes/<plane>/maps/map/vault/*.tmx

HAND-AUTHORED, never touched here: config.json, world/world.json,
world/biomes/*.json, world/shops.json, world/quests.json, town_names_*.txt.

WHY ONE ENEMY ENTRY PER DECK, and not one enemy with deckOverride:

  The Tiled enemy template exposes a `deckOverride` property that looks like
  the way to point twenty-one copies of one enemy at twenty-one decks. It is
  not. MapStage calls EnemySprite.overrideDeck(path), which assigns to
  this.data.deck on the EnemyData handed back by WorldData.getEnemy(name) -
  and that is the shared instance out of a STATIC cache loaded once per
  process. Twenty-one map objects sharing one enemy name therefore all end up
  on whichever override was applied last, for the rest of the session. Stock
  content never puts more than one deckOverride on a name in a single map, so
  the collision is untested upstream. One enemies.json entry per deck avoids
  the whole question.

WHY spawnRate IS 0 ON EVERY ROAMER: these decks belong in the vault, not
wandering the overworld. The biome's own enemy list is empty as well, so the
overworld stays a quiet walk between the town and the vault door.

MAP GEOMETRY: each floor is two rows of chambers around a central corridor.

    +--------+--------+--------+     chamber: 1 roamer, themed floor, pacing
    | [#] o  | [#] o  | [#] o  |              on one of six routes, chests [#]
    |   ~~   |   ~~   |   ~~   |     corridor: connects every chamber, with
    +---||---+---||---+---||---+---+          the way back at the far left, and
    |>>                      |...=|          a walled stair landing at the far
    +---||---+---||---+------+---+            right whose own stonework and run
    |   ~~   |   ~~   |                       of steps make the descent to the
    | [#] o  | [#] o  |                       next floor visible, not a surprise
    +--------+--------+

Each chamber's floor is themed from its commander's creature type (a vampire
gets crypt stone, an elf gets grove) with a colour-identity fallback, and no two
rooms on a floor share a theme. Decoration, chest count and side loot all scale
with the deck's score, so a deep room reads as luxurious at a glance.

Floors are ordered by deck score, weakest first, so the descent tracks power.

TWO ENGINE CONTRACTS THIS GENERATOR EXISTS TO SATISFY, both silent when broken:

  1. EXACTLY ONE TILE LAYER MUST CARRY spriteLayer=true. PointOfInterestMapRenderer
     iterates the layers and calls stage.draw(batch) only on the layer that is
     identical to MapStage.spriteLayer. With no such layer the comparison never
     matches, so the player, the enemies and the chests are NEVER DRAWN - the
     tiles render perfectly and the map looks empty. MapStage prints "Warning:
     No spriteLayer present in map." to stderr and carries on.

  2. THE MAP MUST BE AT LEAST AS LARGE AS THE VIEWPORT, config.json's
     screenWidth x screenHeight in pixels. A shorter map leaves the camera with
     nothing to scroll against.
"""
import argparse
import base64
import hashlib
import json
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

PLANE = "Archidekt_Vaults"
FLOORS = 3

# --- tile ids, taken from stock cave maps in common/maps/map/cave/ ----------
# GID 2430 is a floor tile with no collision shapes; GID 2374 is solid rock and
# DOES carry collision shapes in main.tsx. Walls are therefore painted rather
# than fenced with collision objects, exactly as the stock caves do it.
GID_FLOOR = 2430
GID_ROCK = 2374
TILE = 16

# Relative path from planes/<plane>/maps/map/vault/ up to res/adventure/.
UP = "../../../../"

# --- chamber geometry, in tiles --------------------------------------------
CHAMBER_W = 9
CHAMBER_H = 8
CORRIDOR_H = 3
BORDER = 1
STAIR_W = 4

COLOR_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}


def stable(*parts):
    """A deterministic integer from strings. The same deck must always draw the
    same avatar, room and patrol, or a resync reshuffles the whole dungeon."""
    h = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return int(h[:8], 16)


# --- sprite resolution -----------------------------------------------------
# Three tiers, best first:
#   1. the sprite the shipped Realm of Legends plane already uses for that exact
#      legend - it is a plane of nothing but commanders, so most of ours are
#      already cast. Derived from its enemies.json rather than hardcoded here.
#   2. the closest match for the commander's own creature types.
#   3. the deck's colour identity.
# Every path is borrowed from common BY PATH and never copied in - a forked
# sprite would be a permanent OWNERSHIP.md row bought for nothing.
RACE_SPRITES = [
    ("Phyrexian", "aberration/phyrexian"), ("Eldrazi", "aberration/eldrazi"),
    ("Vampire", "undead/vampire"), ("Zombie", "undead/zombie"),
    ("Skeleton", "undead/skeleton"), ("Spirit", "undead/ghost"),
    ("Angel", "celestial/angel"), ("Demon", "fiend/demon"), ("Devil", "fiend/"),
    ("Dragon", "dragon/"), ("Djinn", "elemental/djinn"), ("Elemental", "elemental/"),
    ("Sphinx", "monstrosity/androsphinx"), ("Hydra", "monstrosity/hydra"),
    ("God", "giant/godlytitan"), ("Titan", "giant/"), ("Giant", "giant/"),
    ("Golem", "construct/golem"), ("Construct", "construct/"),
    ("Treefolk", "plant/"), ("Fungus", "plant/fungus"), ("Plant", "plant/"),
    ("Ooze", "ooze/"), ("Satyr", "fey/satyr"), ("Centaur", "fey/centaur"),
    ("Faerie", "fey/"), ("Elf", "humanoid/elf"), ("Goblin", "humanoid/goblin"),
    ("Merfolk", "humanoid/merfolk"), ("Dwarf", "humanoid/dwarf"),
    ("Minotaur", "humanoid/minotaur"), ("Naga", "humanoid/naga"),
    ("Leonin", "humanoid/leonin"), ("Kor", "humanoid/kor"), ("Aven", "humanoid/aven"),
    ("Rat", "humanoid/nezumi"), ("Cat", "beast/cat"), ("Bird", "beast/bird"),
    ("Insect", "beast/insect"), ("Spider", "beast/arachnid"), ("Beast", "beast/"),
    # class fallbacks, for Humans and anything else with a generic body
    ("Monk", "humanoid/human/cleric/monk"), ("Cleric", "humanoid/human/cleric"),
    ("Knight", "humanoid/human/knight"), ("Noble", "humanoid/human/knight"),
    ("Assassin", "humanoid/human/rogue"), ("Rogue", "humanoid/human/rogue"),
    ("Warlock", "humanoid/human/warlock"), ("Wizard", "humanoid/human/wizard"),
    ("Druid", "humanoid/elf/druid"), ("Shaman", "humanoid/human/shaman"),
    ("Artificer", "humanoid/human/artificer"), ("Scientist", "humanoid/human/artificer"),
    ("Archer", "humanoid/human/archer"), ("Bard", "humanoid/human/bard"),
    ("Soldier", "humanoid/human/soldier"), ("Warrior", "humanoid/human/warrior"),
    ("Human", "humanoid/human/"),
]
COLOR_SPRITES = {
    "W": "humanoid/human/wizard/white_wiz", "U": "humanoid/human/wizard/blue_wiz",
    "B": "humanoid/human/wizard/black_wiz", "R": "humanoid/human/wizard/red_wiz",
    "G": "humanoid/human/wizard/green_wiz", "C": "construct/",
}


def common_atlases():
    """Every enemy atlas in the common layer, as a plane-relative path."""
    if hasattr(common_atlases, "_cache"):
        return common_atlases._cache
    root = C.ref("forge-common")
    out = []
    if root:
        base = os.path.join(root, "sprites", "enemy")
        for dirpath, _d, files in os.walk(base):
            for fn in sorted(files):
                if fn.endswith(".atlas"):
                    rel = os.path.relpath(os.path.join(dirpath, fn), root)
                    out.append(rel.replace(os.sep, "/"))
    common_atlases._cache = sorted(out)
    return common_atlases._cache


def legend_sprites():
    """{legend name -> sprite path} from the shipped Realm of Legends plane.

    Read-only, and only the path STRING is taken: those paths point back into
    common/, which this plane already resolves by fallback, so borrowing one
    copies nothing and adds no ownership row. Absent install, absent plane or a
    renamed file all degrade to the type-based tier rather than failing.
    """
    if hasattr(legend_sprites, "_cache"):
        return legend_sprites._cache
    index = {}
    root = C.install_root()
    path = (os.path.join(root, "res", "adventure", "Realm of Legends", "world", "enemies.json")
            if root else None)
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                for e in json.load(f):
                    if e.get("name") and e.get("sprite"):
                        index[e["name"].strip().lower()] = e["sprite"]
        except (OSError, ValueError):
            pass
    legend_sprites._cache = index
    return index


def pick_sprite(deck):
    """(sprite path, which tier answered) for one roamer."""
    atlases = common_atlases()
    slug = deck["slug"]

    legends = legend_sprites()
    for full in (deck.get("commanders") or []):
        if not full:
            continue
        for key in (full, full.split(",")[0], full.split(" of ")[0]):
            hit = legends.get(key.strip().lower())
            if hit:
                return hit, "legend"

    def from_fragment(fragment):
        pool = [a for a in atlases if fragment in a]
        return pool[stable(slug, fragment) % len(pool)] if pool else None

    for ctype, fragment in RACE_SPRITES:
        if ctype in (deck.get("commanderTypes") or []):
            hit = from_fragment(fragment)
            if hit:
                return hit, "type:" + ctype

    colors = deck.get("colors") or "C"
    key = "C" if len(colors) >= 3 else colors[:1]
    return (from_fragment(COLOR_SPRITES.get(key, "construct/"))
            or "sprites/enemy/humanoid/conjurer.atlas"), "colour"


# --- room themes -----------------------------------------------------------
# Floor tile ids, each lifted from the Background layer of the stock dungeon
# family it is named after, so every one is a tile Forge already uses as walkable
# ground. All are verified collision-free; verify.py's tile-collision check
# re-proves it on every run, because a colliding floor tile makes a sealed room.
THEME_FLOORS = {
    "skullcave": 221, "demontower": 764, "maze": 1133, "catlair": 1149,
    "evilgrove": 1165, "zedruu": 1765, "monastery": 2020, "cave": 2382,
    "barbariancamp": 2393, "grove": 2406, "grolnok": 2422, "hostiletown": 2425,
    "jacetower": 2430, "aerie": 2438, "merfolkpool": 2446, "crypt": 2454,
    "fort": 2457, "tibalt": 2516, "lavaforge": 2519, "djinnpalace": 2856,
    "towns": 2936, "magetower": 2946, "emrakul": 5062, "snowabbey": 5560,
    "phyrexia": 11905,
}
RACE_THEMES = [
    ("Vampire", "crypt"), ("Zombie", "crypt"), ("Skeleton", "skullcave"),
    ("Spirit", "skullcave"), ("Demon", "demontower"), ("God", "demontower"),
    ("Devil", "lavaforge"), ("Dragon", "aerie"), ("Angel", "monastery"),
    ("Cleric", "monastery"), ("Phyrexian", "phyrexia"), ("Golem", "phyrexia"),
    ("Construct", "phyrexia"), ("Artificer", "phyrexia"), ("Merfolk", "merfolkpool"),
    ("Elemental", "lavaforge"), ("Elf", "grove"), ("Treefolk", "grove"),
    ("Satyr", "grove"), ("Plant", "evilgrove"), ("Fungus", "evilgrove"),
    ("Cat", "catlair"), ("Leonin", "catlair"), ("Goblin", "barbariancamp"),
    ("Minotaur", "barbariancamp"), ("Sphinx", "djinnpalace"), ("Djinn", "djinnpalace"),
    ("Wizard", "magetower"), ("Warlock", "magetower"), ("Knight", "fort"),
    ("Noble", "fort"), ("Rat", "maze"), ("Rogue", "hostiletown"),
    ("Assassin", "hostiletown"), ("Frog", "grolnok"), ("Eldrazi", "emrakul"),
]
COLOR_THEMES = {"W": "monastery", "U": "merfolkpool", "B": "crypt",
                "R": "lavaforge", "G": "grove", "C": "cave"}
MULTI_THEME = "magetower"
# Drawn from when two roamers on one floor would otherwise share a theme.
ALTERNATE_THEMES = ["snowabbey", "fort", "zedruu", "towns", "aerie", "maze", "catlair",
                    "grolnok", "tibalt", "djinnpalace", "hostiletown", "skullcave",
                    "demontower", "barbariancamp", "evilgrove", "jacetower", "cave",
                    "emrakul", "phyrexia", "magetower"]
# Rugs are drawn only from worked-interior floors, so an inlay reads as masonry
# in any room. Picking freely from ALTERNATE_THEMES instead puts snow in the
# lavaforge and a swamp in the abbey.
ACCENT_THEMES = ["fort", "towns", "monastery", "snowabbey"]
# The stair landing is deliberately NOT in either rotation - it must read as the
# same kind of place on every floor.
STAIR_FLOOR = THEME_FLOORS["fort"]


def pick_theme(deck, used):
    """A room theme for this deck that nothing else on the floor is using."""
    want = None
    for ctype, theme in RACE_THEMES:
        if ctype in (deck.get("commanderTypes") or []):
            want = theme
            break
    if want is None:
        colors = deck.get("colors") or "C"
        want = MULTI_THEME if len(colors) >= 3 else COLOR_THEMES.get(colors[:1], "cave")
    if want not in used:
        return want
    start = stable(deck["slug"]) % len(ALTERNATE_THEMES)
    for i in range(len(ALTERNATE_THEMES)):
        alt = ALTERNATE_THEMES[(start + i) % len(ALTERNATE_THEMES)]
        if alt not in used:
            return alt
    return want


# --- rewards ---------------------------------------------------------------
# --- duplicate-free deck hauls ---------------------------------------------
# The engine draws card rewards WITH REPLACEMENT and offers no switch:
# CardUtil.generateCards() loops `count` times over
# `filtered.get(rand.nextInt(filtered.size()))` and never removes what it drew,
# so one `deckCard` entry asking for nine cards can hand back the same card
# nine times. Worse, the deckCard pool is Deck.getAllCardsInASinglePool()
# .toFlatList(), so a Commander deck's 7-15 basic lands are that many separate
# entries and dominate the draw.
#
# The fix is to stop asking one entry for nine cards. A haul is emitted as one
# single-draw entry per BUCKET, and the buckets are chosen so no card can sit in
# two of them:
#   * rarity is exclusive per printing (CardPredicate does
#     rarities.contains(card.getRarity())), and
#   * the mana-cost bands partition the curve.
# One draw per bucket, disjoint buckets, therefore no duplicate is possible.
#
# Never listing `BasicLand` also drops basics from the haul entirely - it is its
# own CardRarity, not a Common.
#
# `addMaxCount` is deliberately absent: it adds difficulty-scaled EXTRA draws to
# the same entry, which would put duplicates straight back. Quantity is set by
# how many buckets a deck earns instead.
CMC_BANDS = {
    "lo": [0, 1, 2],
    "mid": [3, 4],
    "hi": [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
}
# Ascending value. Measured over the 21 real decks: the eight from Uncommon/lo
# up are never empty, Common/mid is empty 5 times in 21 and Mythic/lo 3 - an
# empty bucket costs one card, never a duplicate. Common/hi and Uncommon/hi are
# left out because they are empty 17 and 8 times in 21.
DECK_BUCKETS = [
    ("Common", "mid"), ("Common", "lo"), ("Uncommon", "lo"), ("Uncommon", "mid"),
    ("Rare", "lo"), ("Rare", "mid"), ("Rare", "hi"),
    ("Mythic Rare", "lo"), ("Mythic Rare", "mid"), ("Mythic Rare", "hi"),
]


def deck_card_haul(deck):
    """One single-draw `deckCard` entry per disjoint bucket.

    Quantity is always generous and grows a little with score; the window slides
    up the value order, so a floor-1 deck gives up commons and uncommons while
    the boss gives up everything including all three mythic bands.
    """
    s = deck["score"]
    n = 6 + round(s * 4)
    start = round(s * (len(DECK_BUCKETS) - n))
    return [{"type": "deckCard", "probability": 1, "count": 1,
             "rarity": [rarity], "manaCosts": CMC_BANDS[band]}
            for rarity, band in DECK_BUCKETS[start:start + n]]


def enemy_rewards(deck, floor):
    """What a roamer drops: a big, duplicate-free slice of its own deck, plus
    the gravy."""
    s = deck["score"]
    haul = deck_card_haul(deck)
    haul.append({"type": "shards", "probability": 1,
                 "count": 2 + round(s * 6), "addMaxCount": 3 + round(s * 10)})
    haul.append({"type": "gold", "probability": 1,
                 "count": 80 + round(s * 620), "addMaxCount": 150 + round(s * 1100)})
    if s >= 0.45:
        # Drawn from the whole legal pool rather than the deck, so it cannot
        # collide with the buckets above in any meaningful way.
        haul.append({"type": "card", "probability": 0.6, "count": 1 + round(s * 2),
                     "rarity": ["Rare", "Mythic Rare"],
                     "colors": [COLOR_NAMES[c] for c in deck["colors"] if c in COLOR_NAMES]})
    return haul


def chest_reward(deck, floor, index):
    """One chest in a roamer's room.

    Map `reward` objects cannot use `deckCard` - the docs are explicit that it
    is enemy-only - so chests carry colour-matched cards, and richer rooms get
    both more chests and better rarity floors.
    """
    s = deck["score"]
    card = {
        "type": "card",
        "count": 1 + round(s * 3),
        "addMaxCount": 2 + round(s * 4),
        "colors": [COLOR_NAMES[ch] for ch in deck["colors"] if ch in COLOR_NAMES],
    }
    if not card["colors"]:
        del card["colors"]
    if floor >= 3 or (floor >= 2 and index == 0):
        card["rarity"] = ["Rare", "Mythic Rare"]
    elif floor >= 2:
        card["rarity"] = ["Uncommon", "Rare"]
    return [card, {"type": "shards", "count": 1 + round(s * 4)}]


def side_loot(deck):
    """Extra lootables strewn round a richer room: (template, reward) pairs.

    Quantity, variety and quality all key off the same score, so a deep room
    reads as luxurious at a glance rather than merely holding a bigger number.
    """
    s = deck["score"]
    out = []
    if s >= 0.25:
        out.append(("gold", [{"type": "gold", "count": 60 + round(s * 400),
                              "addMaxCount": 80 + round(s * 700)}]))
    if s >= 0.40:
        out.append(("manashards", [{"type": "shards", "count": 2 + round(s * 5),
                                    "addMaxCount": 3 + round(s * 7)}]))
    if s >= 0.55:
        out.append(("booster", [{"type": "card", "count": 3 + round(s * 4),
                                 "addMaxCount": 2 + round(s * 4),
                                 "rarity": ["Uncommon", "Rare"]}]))
    if s >= 0.75:
        out.append(("treasure", [{"type": "card", "count": 2 + round(s * 3),
                                  "rarity": ["Rare", "Mythic Rare"],
                                  "colors": [COLOR_NAMES[c] for c in deck["colors"]
                                             if c in COLOR_NAMES]}]))
    return out


# --- tmx emission ----------------------------------------------------------
def encode_layer(grid):
    raw = b"".join(struct.pack("<I", g) for row in grid for g in row)
    return base64.b64encode(zlib.compress(raw)).decode("ascii")


def xml_attr(v):
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def prop(name, value, ptype=None):
    t = ' type="%s"' % ptype if ptype else ""
    return '    <property name="%s"%s value="%s"/>' % (name, t, xml_attr(value))


def build_floor(user, floor, decks, out_path, prev_map, next_map, min_tiles):
    """Write one floor. decks are already ordered weakest-first."""
    top = decks[:(len(decks) + 1) // 2]
    bottom = decks[(len(decks) + 1) // 2:]
    cols = max(1, len(top), len(bottom))

    min_w, min_h = min_tiles
    body_w = BORDER * 2 + cols * CHAMBER_W
    landing = STAIR_W + 1 if next_map else 0          # +1 for the dividing wall
    w = max(min_w, body_w + landing)
    h = max(min_h, BORDER * 2 + CHAMBER_H * 2 + CORRIDOR_H)

    rock = [[GID_ROCK] * w for _ in range(h)]
    floor_layer = [[THEME_FLOORS["cave"]] * w for _ in range(h)]
    blank = [[0] * w for _ in range(h)]

    corr_top = BORDER + CHAMBER_H
    corr_rows = list(range(corr_top, corr_top + CORRIDOR_H))
    mid_row = corr_top + 1
    for r in corr_rows:
        for c in range(BORDER, w - BORDER):
            rock[r][c] = 0
            floor_layer[r][c] = THEME_FLOORS["towns"]

    objects = []
    ID_UP, ID_DOWN = 2, 3
    state = {"id": 10}
    notes = []

    # Themes are claimed strongest-first, so the floor's best deck gets the room
    # its commander actually asks for and the weaker ones take the alternates.
    used_themes = set()
    themes = {}
    for d in sorted(decks, key=lambda x: -x["score"]):
        themes[d["slug"]] = pick_theme(d, used_themes)
        used_themes.add(themes[d["slug"]])

    def obj(template, col, row, props=None):
        body = ""
        if props:
            body = "\n   <properties>\n%s\n   </properties>\n  " % "\n".join(props)
        objects.append('  <object id="%d" template="%scommon/maps/obj/%s.tx" '
                       'x="%d" y="%d">%s</object>'
                       % (state["id"], UP, template, col * TILE, (row + 1) * TILE, body))
        state["id"] += 1

    def reward_prop(reward):
        return ('    <property name="reward">%s</property>'
                % xml_attr(json.dumps(reward, indent=1)))

    def patrol(x0, x1, ry0, ry1, seed):
        """One of six routes, so no two neighbours trace the same circle."""
        cx = (x0 + x1) // 2
        side = x0 if seed % 2 else x1
        shapes = [
            [(x0, ry0), (x1, ry0), (x1, ry1), (x0, ry1)],          # full perimeter
            [(x0, ry1), (x1, ry1)],                                # front sweep
            [(side, ry0), (side, ry1)],                            # one flank
            [(cx, ry0), (x1, ry1), (x0, ry1)],                     # triangle
            [(x0, ry0), (x1, ry1), (x1, ry0), (x0, ry1)],          # diagonal cross
            [(cx - 2, ry0 + 1), (cx + 2, ry0 + 1),
             (cx + 2, ry1 - 1), (cx - 2, ry1 - 1)],                # tight inner loop
        ]
        pts = shapes[seed % len(shapes)]
        return pts[::-1] if seed % 4 == 3 else pts

    def carve(deck, i, upper):
        """Open one chamber, theme its floor, and stock it."""
        x0 = BORDER + i * CHAMBER_W + 1
        x1 = x0 + CHAMBER_W - 3
        if upper:
            ry0, ry1 = BORDER, corr_top - 2
            door_row = corr_top - 1
            back, mid = BORDER, BORDER + 3
        else:
            ry0, ry1 = corr_top + CORRIDOR_H + 1, h - BORDER - 1
            door_row = corr_top + CORRIDOR_H
            back, mid = h - BORDER - 1, h - BORDER - 4

        theme = themes[deck["slug"]]
        base = THEME_FLOORS[theme]
        s = deck["score"]
        accents = [t for t in ACCENT_THEMES if t != theme] or ACCENT_THEMES
        rug = THEME_FLOORS[accents[stable(deck["slug"], "rug") % len(accents)]]

        for r in range(ry0, ry1 + 1):
            for c in range(x0, x1 + 1):
                rock[r][c] = 0
                floor_layer[r][c] = base
        # Decoration scales with the deck: a plain cell low down, a rug in the
        # middle tiers, a rug with an inlaid core at the top.
        if s >= 0.35:
            for r in range(ry0 + 1, ry1):
                for c in range(x0 + 1, x1):
                    floor_layer[r][c] = rug
        if s >= 0.70:
            for r in range(ry0 + 2, ry1 - 1):
                for c in range(x0 + 2, x1 - 1):
                    floor_layer[r][c] = base
        door = (x0 + x1) // 2
        rock[door_row][door] = 0
        floor_layer[door_row][door] = THEME_FLOORS["towns"]

        seed = stable(deck["slug"], "patrol")
        wp = []
        for (cx, cy) in patrol(x0, x1, ry0 + 1, ry1 - 1, seed):
            wp.append(state["id"])
            obj("waypoint", cx, cy)
        route = wp if seed % 2 else wp + wp[-2:0:-1]

        obj("enemy", door, mid, [
            prop("enemy", deck["enemyName"]),
            prop("threatRange", 18 + seed % 22, "int"),
            prop("pursueRange", 10 + (seed >> 3) % 18, "int"),
            prop("waypoints", ",".join(str(x) for x in route)),
        ])

        chests = 1 + int(s * 2.4)
        spread = {1: [0], 2: [-2, 2], 3: [-3, 0, 3]}[min(chests, 3)]
        for n, dx in enumerate(spread):
            obj("treasure", door + dx, back, [reward_prop(chest_reward(deck, floor, n))])
        extras = side_loot(deck)
        corners = [(x0, back), (x1, back),
                   (x0, ry1 if upper else ry0), (x1, ry1 if upper else ry0)]
        for n, (template, reward) in enumerate(extras):
            col, row = corners[n % len(corners)]
            obj(template, col, row, [reward_prop(reward)])
        notes.append("%-30s %-13s %d chest(s) + %d extra"
                     % (deck["name"][:30], theme, chests, len(extras)))

    for i, deck in enumerate(top):
        carve(deck, i, True)
    for i, deck in enumerate(bottom):
        carve(deck, i, False)

    # `direction` names the side the entry FACES, and the player is placed on
    # the OPPOSITE side. EntryActor.spawn() is unambiguous:
    #     "left"  -> setPosition(x + w, ...)            player to the RIGHT
    #     "right" -> setPosition(x - playerWidth, ...)  player to the LEFT
    # The shipped doc reads the other way round and is wrong.
    for c in range(BORDER, BORDER + 3):
        for r in corr_rows:
            floor_layer[r][c] = STAIR_FLOOR
    objects.insert(0,
        '  <object id="%d" template="%scommon/maps/obj/entry_up.tx" x="%d" y="%d">\n'
        '   <properties>\n%s\n   </properties>\n  </object>'
        % (ID_UP, UP, BORDER * TILE, (mid_row + 1) * TILE,
           "\n".join([prop("direction", "left"),
                      prop("teleport", prev_map or ""),
                      prop("teleportObjectId", str(ID_DOWN) if prev_map else "")])))

    if next_map:
        # A walled stair landing off the end of the corridor, floored in its own
        # stone with a run of steps before the door, so "there is another floor
        # below" is something you can see rather than something you bump into.
        wall_col = w - BORDER - STAIR_W - 1
        for r in corr_rows:
            rock[r][wall_col] = GID_ROCK
        rock[mid_row][wall_col] = 0
        floor_layer[mid_row][wall_col] = STAIR_FLOOR
        for r in corr_rows:
            for c in range(wall_col + 1, w - BORDER):
                rock[r][c] = 0
                floor_layer[r][c] = STAIR_FLOOR
        for n, c in enumerate(range(w - BORDER - 3, w - BORDER)):
            step = THEME_FLOORS["snowabbey" if n % 2 else "zedruu"]
            for r in corr_rows:
                floor_layer[r][c] = step
        objects.append(
            '  <object id="%d" template="%scommon/maps/obj/entry_down.tx" x="%d" y="%d">\n'
            '   <properties>\n%s\n   </properties>\n  </object>'
            % (ID_DOWN, UP, (w - BORDER - 1) * TILE, (mid_row + 1) * TILE,
               "\n".join([prop("direction", "right"),
                          prop("teleport", next_map),
                          prop("teleportObjectId", str(ID_UP))])))

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<map version="1.10" tiledversion="1.10.1" orientation="orthogonal" '
        'renderorder="right-down" width="%d" height="%d" tilewidth="16" tileheight="16" '
        'infinite="0" nextlayerid="6" nextobjectid="%d">' % (w, h, state["id"] + 1),
        ' <tileset firstgid="1" source="%scommon/maps/tileset/main.tsx"/>' % UP,
        ' <layer id="1" name="Background" width="%d" height="%d">' % (w, h),
        '  <data encoding="base64" compression="zlib">%s</data>' % encode_layer(floor_layer),
        ' </layer>',
        ' <layer id="2" name="Ground" width="%d" height="%d">' % (w, h),
        '  <data encoding="base64" compression="zlib">%s</data>' % encode_layer(rock),
        ' </layer>',
        # Empty on purpose. Its ONLY job is to carry spriteLayer=true, which is
        # what makes PointOfInterestMapRenderer call stage.draw(batch) at all -
        # without it the player, enemies and chests are never drawn.
        ' <layer id="3" name="Foreground" width="%d" height="%d">' % (w, h),
        '  <properties>',
        '   <property name="spriteLayer" type="bool" value="true"/>',
        '  </properties>',
        '  <data encoding="base64" compression="zlib">%s</data>' % encode_layer(blank),
        ' </layer>',
        ' <objectgroup id="4" name="Objects">',
    ]
    xml.extend(objects)
    xml.append(' </objectgroup>')
    xml.append('</map>')

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(xml) + "\n")
    return w, h, notes


# --- generation ------------------------------------------------------------
def load_rosters(plane):
    root = os.path.join(C.REPO, "planes", plane, "decks")
    rosters = []
    if not os.path.isdir(root):
        return rosters
    for d in sorted(os.listdir(root)):
        p = os.path.join(root, d, "_roster.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                rosters.append(json.load(f))
    return rosters


def split_floors(decks, floors):
    """Weakest-first, into `floors` groups of near-equal size."""
    ordered = sorted(decks, key=lambda d: d["score"])
    n = len(ordered)
    out, start = [], 0
    for i in range(floors):
        take = (n - start) // (floors - i)
        out.append(ordered[start:start + take])
        start += take
    return out


def sync_biome_pois(path, names):
    """Rewrite just the pointsOfInterest array of an authored biome file."""
    if not os.path.exists(path):
        raise SystemExit("missing hand-authored biome %s - the vault POIs have "
                         "nowhere to be placed" % path)
    with open(path, encoding="utf-8") as f:
        biome = json.load(f)
    biome["pointsOfInterest"] = names
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(biome, f, indent=2)
        f.write("\n")


def generate(plane, floors):
    rosters = load_rosters(plane)
    if not rosters:
        raise SystemExit("no roster found under planes/%s/decks/ - run "
                         "tools/archidekt_sync.py first" % plane)

    # A map smaller than the viewport leaves the camera nothing to scroll
    # against, so the floor size floor comes from the plane's own config.
    with open(os.path.join(C.REPO, "planes", plane, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    min_tiles = (-(-cfg.get("screenWidth", 480) // TILE),
                 -(-cfg.get("screenHeight", 270) // TILE))

    enemies, pois, made = [], [], []
    for roster in rosters:
        user, uslug = roster["user"], roster["userSlug"]
        kept = [d for d in roster["decks"] if d.get("kept")]
        if not kept:
            print("  %s: no legal decks, skipping" % user)
            continue
        for d in kept:
            d["enemyName"] = "%s_%s" % (uslug, d["slug"])
        by_floor = split_floors(kept, floors)
        top = max(kept, key=lambda d: d["score"])

        tiers = {"legend": 0, "type": 0, "colour": 0}
        for fi, group in enumerate(by_floor, start=1):
            for d in group:
                s = d["score"]
                sprite, tier = pick_sprite(d)
                tiers[tier.split(":")[0]] += 1
                e = {
                    "name": d["enemyName"],
                    "nameOverride": d["name"],
                    "sprite": sprite,
                    "deck": [d["deckPath"]],
                    "ai": "",
                    "spawnRate": 0,
                    "difficulty": round(s, 3),
                    # A jittered speed so neighbouring roamers do not pace in
                    # lockstep; the patrol shapes vary independently.
                    "speed": 20 + round(s * 14) + stable(d["slug"], "speed") % 7,
                    "life": 18 + round(s * 32),
                    "colors": d["colors"],
                    "rewards": enemy_rewards(d, fi),
                    "questTags": ["ArchidektVault", "Vault_" + uslug,
                                  "VaultFloor%d" % fi],
                }
                if d is top:
                    e["boss"] = True
                    e["gamesPerMatch"] = 3
                enemies.append(e)

        vault_dir = os.path.join(C.REPO, "planes", plane, "maps", "map", "vault")
        for fi, group in enumerate(by_floor, start=1):
            rel = "../%s/maps/map/vault/%s_f%d.tmx" % (plane, uslug, fi)
            prev_rel = ("../%s/maps/map/vault/%s_f%d.tmx" % (plane, uslug, fi - 1)
                        if fi > 1 else None)
            next_rel = ("../%s/maps/map/vault/%s_f%d.tmx" % (plane, uslug, fi + 1)
                        if fi < len(by_floor) else None)
            w, h, notes = build_floor(user, fi, group,
                                      os.path.join(vault_dir, "%s_f%d.tmx" % (uslug, fi)),
                                      prev_rel, next_rel, min_tiles)
            made.append("%s_f%d.tmx  %dx%d  %d roamer(s)" % (uslug, fi, w, h, len(group)))
            made.extend("    " + n for n in notes)

        pois.append({
            "name": "Vault_" + uslug,
            "displayName": "%s's Vault" % user,
            "type": "dungeon",
            "count": 1,
            "spriteAtlas": "../common/maps/tileset/buildings.atlas",
            "sprite": "MageTower",
            "map": "../%s/maps/map/vault/%s_f1.tmx" % (plane, uslug),
            "radiusFactor": 0.8,
            "questTags": ["ArchidektVault", "Dungeon", "Hostile"],
        })
        print("  %s: %d roamers across %d floors  (sprites: %d from Realm of Legends, "
              "%d by creature type, %d by colour)"
              % (user, len(kept), len(by_floor), tiers["legend"], tiers["type"],
                 tiers["colour"]))

    pois.insert(0, {
        "name": "Vault Town",
        "displayName": "Deckwright",
        "type": "town",
        "count": 1,
        "spriteAtlas": "../common/maps/tileset/buildings.atlas",
        "sprite": "PlainsTown",
        "map": "../common/maps/map/towns/plains_town_generic.tmx",
        "radiusFactor": 0.8,
        "questTags": ["Town", "TownGeneric", "QuestSource"],
    })

    world = os.path.join(C.REPO, "planes", plane, "world")
    os.makedirs(world, exist_ok=True)
    for fn, data in (("enemies.json", enemies), ("points_of_interest.json", pois)):
        with open(os.path.join(world, fn), "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=1)
            f.write("\n")

    # The biome file is hand-authored art and terrain, but its POI list is
    # derived: a POI that no biome names is never placed on the overworld, so
    # letting a human maintain that list by hand is a silent-loss bug waiting
    # to happen. Only this one array is rewritten.
    sync_biome_pois(os.path.join(world, "biomes", "vault.json"),
                    [p["name"] for p in pois])

    print("\ngenerated %d enemies, %d POIs" % (len(enemies), len(pois)))
    for m in made:
        print("  " + m)
    print("\nnext: python tools/verify.py > verify-report.txt")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plane", default=PLANE)
    ap.add_argument("--floors", type=int, default=FLOORS)
    a = ap.parse_args()
    generate(a.plane, a.floors)


if __name__ == "__main__":
    main()
