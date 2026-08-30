# -*- coding: utf-8 -*-
"""ForgeModding verify gate - the content linter, plus the engine-track check.

WHAT THIS IS: this project's verify method (PROJECT.md). Run it after every
content change and read the report:

    python tools/verify.py > verify-report.txt

WHY IT EXISTS: Forge's failure mode for bad content is SILENT FALLBACK, not an
error. A plane with an unresolvable sprite path, a missing deck, or a card name
that does not exist loads happily and simply shows less than you authored. The
relaunch loop is minutes; this is seconds.

THREE OUTCOMES, and the distinction is the point:
  FAIL     - content is wrong; fix it.
  BLOCKED  - the check could not run because a machine prerequisite is missing.
             Named explicitly, never skipped quietly: a linter that silently
             does less than it claims turns an unchecked repo into one that
             LOOKS checked.
  TODO     - a check named in docs/ARCHITECTURE.md that is not implemented yet.
             Listed on every run so the gap between promise and behaviour stays
             visible here rather than buried in a doc.

Exit code: 0 when nothing FAILed, 1 otherwise. BLOCKED and TODO do not fail the
run - they are machine and roadmap state, not content defects.
"""
import base64
import io
import json
import os
import re
import subprocess
import sys
import zipfile
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

RESULTS = []
_FLUSHED = 0


def emit(status, check, detail=""):
    RESULTS.append((status, check, detail))


def _flush():
    """Print results accumulated since the last section, so each check lands
    under the heading it belongs to rather than in one undifferentiated dump."""
    global _FLUSHED
    for status, check, detail in RESULTS[_FLUSHED:]:
        print("%-8s %-26s %s" % (status, check, detail))
    _FLUSHED = len(RESULTS)


def section(title):
    _flush()
    print("\n" + title)
    print("-" * len(title))


# --------------------------------------------------------------------------
# check 1 - every JSON parses
# --------------------------------------------------------------------------
def check_json_parses():
    bad = 0
    total = 0
    for root in ("planes", "custom"):
        base = os.path.join(C.REPO, root)
        for dirpath, _dirnames, filenames in os.walk(base):
            for fn in filenames:
                if not fn.endswith(".json"):
                    continue
                total += 1
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, C.REPO)
                try:
                    with io.open(path, encoding="utf-8") as f:
                        json.load(f)
                except ValueError as e:
                    bad += 1
                    emit("FAIL", "json-parse", "%s: %s" % (rel, e))
                except OSError as e:
                    bad += 1
                    emit("FAIL", "json-parse", "%s: %s" % (rel, e))
    if not bad:
        emit("PASS", "json-parse", "%d file(s) parse" % total)


# --------------------------------------------------------------------------
# helpers for the resolution checks
# --------------------------------------------------------------------------
def plane_file(plane, relpath):
    """Resolve a plane-relative path the way Forge does: plane first, then
    common. Returns (abs_path, 'plane'|'common') or (None, None)."""
    p = os.path.join(C.REPO, "planes", plane, relpath)
    if os.path.exists(p):
        return p, "plane"
    common = C.ref("forge-common")
    if common:
        p = os.path.join(common, relpath)
        if os.path.exists(p):
            return p, "common"
    return None, None


def load_plane_json(plane, relpath):
    path, origin = plane_file(plane, relpath)
    if not path:
        return None, None
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f), origin
    except (OSError, ValueError):
        return None, origin


def atlas_regions(atlas_path):
    """Region names in a libGDX .atlas. The format is plain text: the header is
    the first block, then region names sit at column 0 and their properties are
    indented. Region names are the animation contract."""
    names = set()
    try:
        with io.open(atlas_path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return names
    for line in lines[1:]:
        if not line or line.startswith((" ", "\t")):
            continue
        if ":" in line.split(" ")[0]:
            continue  # header key like "size:" / "format:"
        names.add(line.strip())
    return names


# --------------------------------------------------------------------------
# check 2 - sprite paths and atlas regions resolve
# --------------------------------------------------------------------------
def check_sprites(plane):
    if not C.ref("forge-common"):
        emit("BLOCKED", "sprite-resolve", "forge-common not bound in references.local.json")
        return
    enemies, _ = load_plane_json(plane, "world/enemies.json")
    if enemies is None:
        emit("BLOCKED", "sprite-resolve", "%s: no enemies.json in plane or common" % plane)
        return
    missing = 0
    checked = 0
    for entry in enemies if isinstance(enemies, list) else []:
        sprite = (entry or {}).get("sprite")
        if not sprite:
            continue
        checked += 1
        path, _origin = plane_file(plane, sprite)
        if not path:
            missing += 1
            emit("FAIL", "sprite-resolve",
                 "%s: enemy %r sprite %r resolves in neither plane nor common"
                 % (plane, entry.get("name", "?"), sprite))
    if not missing:
        emit("PASS", "sprite-resolve", "%s: %d sprite path(s) resolve" % (plane, checked))


# --------------------------------------------------------------------------
# check 3 - deck files resolve, and every card name in them resolves
# --------------------------------------------------------------------------
def stock_card_names():
    """Card names from cardsfolder.zip + tokenscripts. This is the expensive
    one, so it is built once and cached on the function."""
    if hasattr(stock_card_names, "_cache"):
        return stock_card_names._cache
    names = set()
    corpus = C.ref("forge-card-corpus")
    if corpus:
        zpath = os.path.join(corpus, "cardsfolder.zip")
        if os.path.exists(zpath):
            try:
                with zipfile.ZipFile(zpath) as z:
                    for info in z.namelist():
                        if not info.endswith(".txt"):
                            continue
                        with z.open(info) as fh:
                            head = fh.read(400).decode("utf-8", "replace")
                        m = re.search(r"^Name:(.+)$", head, re.M)
                        if m:
                            names.add(m.group(1).strip())
            except (OSError, zipfile.BadZipFile):
                pass
        for dirpath, _d, filenames in os.walk(corpus):
            for fn in filenames:
                if fn.endswith(".txt"):
                    names |= _names_in_script(os.path.join(dirpath, fn))
    tokens = C.ref("forge-token-corpus")
    if tokens:
        for dirpath, _d, filenames in os.walk(tokens):
            for fn in filenames:
                if fn.endswith(".txt"):
                    names |= _names_in_script(os.path.join(dirpath, fn))
    stock_card_names._cache = names
    return names


def _names_in_script(path):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(400)
    except OSError:
        return set()
    m = re.search(r"^Name:(.+)$", head, re.M)
    return {m.group(1).strip()} if m else set()


def custom_card_names(plane):
    """Adventure-only cards: the plane's custom_cards/ plus common's."""
    names = set()
    for base, _origin in (
        (os.path.join(C.REPO, "planes", plane, "custom_cards"), "plane"),
        (os.path.join(C.ref("forge-common") or "", "custom_cards"), "common"),
    ):
        if base and os.path.isdir(base):
            for dirpath, _d, filenames in os.walk(base):
                for fn in filenames:
                    if fn.endswith(".txt"):
                        names |= _names_in_script(os.path.join(dirpath, fn))
    global_custom = os.path.join(C.REPO, "custom", "cards")
    if os.path.isdir(global_custom):
        for dirpath, _d, filenames in os.walk(global_custom):
            for fn in filenames:
                if fn.endswith(".txt"):
                    names |= _names_in_script(os.path.join(dirpath, fn))
    return names


def deck_card_names(dck_path):
    """Card names in a .dck. Lines look like '4 Lightning Bolt' inside
    [Main]/[Sideboard] sections; a '|SET|num' suffix may follow the name."""
    out = []
    try:
        with io.open(dck_path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    in_cards = False
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("["):
            in_cards = s.lower() in ("[main]", "[sideboard]", "[commander]", "[planes]")
            continue
        if not in_cards:
            continue
        m = re.match(r"^(\d+)\s+(.+)$", s)
        if m:
            out.append(m.group(2).split("|")[0].strip())
    return out


def check_decks(plane):
    if not C.ref("forge-card-corpus"):
        emit("BLOCKED", "deck-card-resolve", "forge-card-corpus not bound in references.local.json")
        return
    known = stock_card_names() | custom_card_names(plane)
    if not known:
        emit("BLOCKED", "deck-card-resolve", "card corpus resolved to 0 names - check the binding")
        return
    deck_root = os.path.join(C.REPO, "planes", plane, "decks")
    if not os.path.isdir(deck_root):
        emit("PASS", "deck-card-resolve", "%s: no plane-local decks" % plane)
        return
    missing = 0
    total = 0
    for dirpath, _d, filenames in os.walk(deck_root):
        for fn in filenames:
            if not fn.endswith(".dck"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, C.REPO)
            for name in deck_card_names(path):
                total += 1
                if name not in known:
                    missing += 1
                    emit("FAIL", "deck-card-resolve", "%s: card %r does not resolve" % (rel, name))
    if not missing:
        emit("PASS", "deck-card-resolve", "%s: %d card name(s) resolve" % (plane, total))


# --------------------------------------------------------------------------
# check 4 - equipment names and item icons
# --------------------------------------------------------------------------
def check_items(plane):
    items, items_origin = load_plane_json(plane, "world/items.json")
    enemies, _ = load_plane_json(plane, "world/enemies.json")
    if items is None:
        emit("BLOCKED", "equipment-resolve", "%s: no items.json in plane or common" % plane)
        return
    if items_origin != "plane":
        # Linting the common fallback means reporting stock defects this repo
        # cannot fix, on every run, for every plane. A linter whose output is
        # mostly noise about someone else's files is a linter people stop
        # reading - so only plane-owned item data is judged here.
        emit("PASS", "equipment-resolve",
             "%s: uses common's items.json unchanged - not linted" % plane)
        return
    item_names = {(i or {}).get("name") for i in (items if isinstance(items, list) else [])}
    bad = 0
    for entry in enemies if isinstance(enemies, list) else []:
        for eq in (entry or {}).get("equipment", []) or []:
            if eq not in item_names:
                bad += 1
                emit("FAIL", "equipment-resolve",
                     "%s: enemy %r equips %r, which is in no effective items list"
                     % (plane, entry.get("name", "?"), eq))
    atlas_path, _ = plane_file(plane, "sprites/items.atlas")
    icons = atlas_regions(atlas_path) if atlas_path else set()
    if not icons:
        emit("BLOCKED", "item-icon-resolve", "%s: items.atlas not resolvable" % plane)
    else:
        for i in items if isinstance(items, list) else []:
            icon = (i or {}).get("iconName")
            if icon and icon not in icons:
                bad += 1
                emit("FAIL", "item-icon-resolve",
                     "%s: item %r iconName %r is not a region in items.atlas"
                     % (plane, i.get("name", "?"), icon))
    if not bad:
        emit("PASS", "equipment-resolve", "%s: equipment and icon names resolve" % plane)


# --------------------------------------------------------------------------
# check 5 - startBattleWithCard* names resolve
# --------------------------------------------------------------------------
def check_battle_cards(plane):
    items, items_origin = load_plane_json(plane, "world/items.json")
    if items is None:
        emit("BLOCKED", "battle-card-resolve", "%s: no items.json" % plane)
        return
    if items_origin != "plane":
        emit("PASS", "battle-card-resolve",
             "%s: uses common's items.json unchanged - not linted" % plane)
        return
    known = stock_card_names() | custom_card_names(plane)
    if not known:
        emit("BLOCKED", "battle-card-resolve", "card corpus unavailable")
        return
    bad = 0
    checked = 0
    for i in items if isinstance(items, list) else []:
        effect = (i or {}).get("effect") or {}
        for key, val in effect.items():
            if not key.startswith("startBattleWithCard"):
                continue
            for name in (val if isinstance(val, list) else [val]):
                checked += 1
                if name not in known:
                    bad += 1
                    emit("FAIL", "battle-card-resolve",
                         "%s: item %r %s references %r, which does not resolve"
                         % (plane, i.get("name", "?"), key, name))
    if not bad:
        emit("PASS", "battle-card-resolve", "%s: %d reference(s) resolve" % (plane, checked))


# --------------------------------------------------------------------------
# check 6 - fork ledger agreement
# --------------------------------------------------------------------------
def check_ownership(plane):
    common = C.ref("forge-common")
    if not common:
        emit("BLOCKED", "ownership-ledger", "forge-common not bound")
        return
    try:
        with io.open(os.path.join(C.REPO, "OWNERSHIP.md"), encoding="utf-8") as f:
            ledger_text = f.read()
    except OSError:
        emit("FAIL", "ownership-ledger", "OWNERSHIP.md is missing")
        return
    # Match ONLY real table rows, never prose or the row template.
    #
    # The template comment in OWNERSHIP.md uses `world/enemies.json` as its
    # worked example. A plain substring search over the whole file therefore
    # reports the single most likely fork in this project as already recorded,
    # which is the exact failure this check exists to prevent.
    ledger_text = re.sub(r"<!--.*?-->", "", ledger_text, flags=re.S)
    ledger = "\n".join(ln for ln in ledger_text.splitlines() if ln.lstrip().startswith("|"))
    # Files that cannot fall back must be shipped per-plane and are not forks.
    MANDATORY = ("world/world.json", "world/quests.json", "world/shops.json")
    plane_root = os.path.join(C.REPO, "planes", plane)
    unrecorded = 0
    for dirpath, _d, filenames in os.walk(plane_root):
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, plane_root).replace(os.sep, "/")
            if rel in MANDATORY or rel.startswith("town_names"):
                continue
            if not os.path.exists(os.path.join(common, rel)):
                continue  # new file, not a fork
            if rel not in ledger:
                unrecorded += 1
                emit("FAIL", "ownership-ledger",
                     "%s: %s also exists in common/ but has no OWNERSHIP.md row - "
                     "shipping it forks that file permanently" % (plane, rel))
    if not unrecorded:
        emit("PASS", "ownership-ledger", "%s: every fork is recorded" % plane)


# --------------------------------------------------------------------------
# engine track
# --------------------------------------------------------------------------
def check_engine():
    patch_dir = os.path.join(C.REPO, "engine", "patches")
    patches = sorted(f for f in os.listdir(patch_dir)) if os.path.isdir(patch_dir) else []
    patches = [p for p in patches if p.endswith(".patch")]
    if not patches:
        emit("PASS", "engine-series", "no patches in the series - nothing to verify")
        return
    ws = C.workspace()
    if not ws or not os.path.isdir(ws):
        emit("BLOCKED", "engine-series",
             "no engine workspace - run python tools/engine_bootstrap.py")
        return
    if not C.tool_available("mvn"):
        emit("BLOCKED", "engine-build", "mvn not installed")
    try:
        r = subprocess.run(["git", "-C", ws, "apply", "--check"] +
                           [os.path.join(patch_dir, p) for p in patches],
                           capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            emit("PASS", "engine-series", "%d patch(es) apply cleanly to the pin" % len(patches))
        else:
            emit("FAIL", "engine-series", r.stderr.strip()[:2000])
    except (OSError, subprocess.SubprocessError) as e:
        emit("BLOCKED", "engine-series", "could not run git apply: %s" % e)


# --------------------------------------------------------------------------
# machine prerequisites, always reported
# --------------------------------------------------------------------------
def check_prereqs():
    for tool, why in (("git", "engine track"), ("mvn", "engine build"), ("adb", "Android deploy")):
        if C.tool_available(tool):
            emit("PASS", "prereq:" + tool, "available")
        else:
            emit("BLOCKED", "prereq:" + tool, "not installed - %s unavailable" % why)
    for rid in ("forge-docs", "forge-common", "forge-card-corpus", "forge-token-corpus"):
        p = C.ref(rid)
        if p and os.path.exists(p):
            emit("PASS", "binding:" + rid, p)
        elif p:
            emit("FAIL", "binding:" + rid, "bound to a path that does not exist: %s" % p)
        else:
            emit("BLOCKED", "binding:" + rid, "not bound in references.local.json")
    if C.workspace():
        emit("PASS", "binding:engine-workspace", C.workspace())
    else:
        emit("BLOCKED", "binding:engine-workspace", "not bootstrapped")


# --------------------------------------------------------------------------
# checks 6-9 - the map/enemy/POI wiring a dungeon plane depends on
#
# Every failure mode below is SILENT in Forge. A mistyped enemy name spawns a
# random biome enemy instead (MapStage prints "Enemy %s not found, choosing a
# random one for current biome" to stdout and carries on); a POI no biome names
# is simply never placed; a 99-card commander deck just plays a card short.
# --------------------------------------------------------------------------
def adventure_path(plane, path):
    """Resolve a path written the way Adventure JSON writes them.

    Forge resolves '../<plane>/...' and '../common/...' against res/adventure.
    In this repo planes/ plays the part of res/adventure and the common layer
    is the bound read-only reference, so both forms are answerable here without
    the install being deployed.
    """
    if not path:
        return None
    p = path.replace("\\", "/")
    if not p.startswith("../"):
        resolved, _origin = plane_file(plane, p)
        return resolved
    rel = p[3:]
    head, _, tail = rel.partition("/")
    if head == "common":
        common = C.ref("forge-common")
        cand = os.path.join(common, tail) if common else None
        return cand if cand and os.path.exists(cand) else None
    cand = os.path.join(C.REPO, "planes", head, tail)
    if os.path.exists(cand):
        return cand
    root = C.install_root()
    if root:
        cand = os.path.join(root, "res", "adventure", head, tail)
        if os.path.exists(cand):
            return cand
    return None


def tmx_files(plane):
    root = os.path.join(C.REPO, "planes", plane, "maps")
    for dirpath, _d, filenames in os.walk(root):
        for fn in sorted(filenames):
            if fn.endswith(".tmx"):
                yield os.path.join(dirpath, fn)


def tmx_objects(path):
    """(properties dict, template) for every <object> in a .tmx."""
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    out = []
    pattern = r"<object\b[^>]*?/>|<object\b[^>]*?>.*?</object>"
    for m in re.finditer(pattern, text, re.S):
        blob = m.group(0)
        tpl = re.search(r'template="([^"]*)"', blob)
        props = dict(re.findall(r'<property name="([^"]*)"[^>]*?value="([^"]*)"', blob))
        for pm in re.finditer(r'<property name="([^"]*)"[^>]*?>(.*?)</property>', blob, re.S):
            props.setdefault(pm.group(1), pm.group(2))
        out.append((props, tpl.group(1) if tpl else None))
    return out


def check_map_enemies(plane):
    """Every `enemy` a map names exists, and no map hands one enemy name two
    different decks.

    The second half is not paranoia. MapStage's deckOverride writes through to
    the EnemyData held in WorldData's STATIC cache, which every sprite of that
    name shares, so two overrides on one name in one map collapse onto the last
    one applied - silently, for the rest of the session.
    """
    enemies, _ = load_plane_json(plane, "world/enemies.json")
    if enemies is None:
        emit("BLOCKED", "map-enemy-resolve", "%s: no enemies.json in plane or common" % plane)
        return
    known = {(e or {}).get("name") for e in (enemies if isinstance(enemies, list) else [])}
    bad = checked = 0
    for path in tmx_files(plane):
        rel = os.path.relpath(path, C.REPO)
        overrides = {}
        for props, _tpl in tmx_objects(path):
            name = props.get("enemy")
            if not name:
                continue
            checked += 1
            if name not in known:
                bad += 1
                emit("FAIL", "map-enemy-resolve",
                     "%s: enemy %r is in no enemies.json - Forge substitutes a "
                     "random biome enemy silently" % (rel, name))
            ovr = props.get("deckOverride") or ""
            if ovr:
                overrides.setdefault(name, set()).add(ovr)
        for name, decks in overrides.items():
            if len(decks) > 1:
                bad += 1
                emit("FAIL", "map-enemy-resolve",
                     "%s: enemy %r carries %d different deckOverride values in one "
                     "map; they collapse onto the last one applied - give each deck "
                     "its own enemies.json entry" % (rel, name, len(decks)))
    if not bad:
        emit("PASS", "map-enemy-resolve",
             "%s: %d map enemy reference(s) resolve" % (plane, checked))


def check_map_links(plane):
    """Every teleport target, object template and tileset a map names exists."""
    bad = checked = 0
    for path in tmx_files(plane):
        rel = os.path.relpath(path, C.REPO)
        here = os.path.dirname(path)
        for props, tpl in tmx_objects(path):
            for ref_path in (tpl, props.get("teleport")):
                if not ref_path:
                    continue
                checked += 1
                cand = os.path.normpath(os.path.join(here, ref_path))
                if os.path.exists(cand):
                    continue
                # Paths that climb out of planes/ land in the install's
                # res/adventure; re-anchor them the way Forge would.
                trimmed = ref_path
                while trimmed.startswith("../"):
                    trimmed = trimmed[3:]
                if adventure_path(plane, "../" + trimmed):
                    continue
                bad += 1
                emit("FAIL", "map-link-resolve", "%s: %r does not resolve" % (rel, ref_path))
        try:
            with io.open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            text = ""
        for src in re.findall(r'<tileset[^>]*source="([^"]*)"', text):
            checked += 1
            cand = os.path.normpath(os.path.join(here, src))
            trimmed = src
            while trimmed.startswith("../"):
                trimmed = trimmed[3:]
            if not os.path.exists(cand) and not adventure_path(plane, "../" + trimmed):
                bad += 1
                emit("FAIL", "map-link-resolve", "%s: tileset %r does not resolve" % (rel, src))
    if not bad:
        emit("PASS", "map-link-resolve",
             "%s: %d map link(s) resolve" % (plane, checked))


def check_tmx_contracts(plane):
    """The two Tiled contracts whose breach is invisible in game.

    spriteLayer: PointOfInterestMapRenderer walks the layers and calls
    stage.draw(batch) only on the layer identical to MapStage.spriteLayer. With
    no layer carrying spriteLayer=true nothing ever matches, so the player, the
    enemies and the chests are never drawn - the tiles render perfectly and the
    map looks empty and unplayable. Forge's only complaint is one line on
    stderr, "Warning: No spriteLayer present in map."

    Size: a map smaller than config.json's screenWidth x screenHeight leaves
    the camera nothing to scroll against.
    """
    cfg, _origin = load_plane_json(plane, "config.json")
    min_w = -(-(cfg or {}).get("screenWidth", 480) // 16)
    min_h = -(-(cfg or {}).get("screenHeight", 270) // 16)
    bad = checked = 0
    for path in tmx_files(plane):
        rel = os.path.relpath(path, C.REPO)
        checked += 1
        try:
            with io.open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        n_sprite = len(re.findall(
            r'<property name="spriteLayer"[^>]*value="true"', text))
        if n_sprite != 1:
            bad += 1
            emit("FAIL", "tmx-contracts",
                 "%s: %d layer(s) carry spriteLayer=true, needs exactly 1 - with "
                 "none, the player and every enemy are silently never drawn"
                 % (rel, n_sprite))
        n_objgroups = len(re.findall(r"<objectgroup\b", text))
        if n_objgroups != 1:
            bad += 1
            emit("FAIL", "tmx-contracts",
                 "%s: %d object layer(s), needs exactly 1" % (rel, n_objgroups))
        m = re.search(r'\bwidth="(\d+)" height="(\d+)" tilewidth="(\d+)" tileheight="(\d+)"',
                      text)
        if not m:
            bad += 1
            emit("FAIL", "tmx-contracts", "%s: no readable map header" % rel)
            continue
        w, h, tw, th = (int(g) for g in m.groups())
        if (tw, th) != (16, 16):
            bad += 1
            emit("FAIL", "tmx-contracts", "%s: %dx%d tiles, Adventure needs 16x16"
                 % (rel, tw, th))
        if w < min_w or h < min_h:
            bad += 1
            emit("FAIL", "tmx-contracts",
                 "%s: %dx%d tiles is smaller than the %dx%d viewport" % (rel, w, h, min_w, min_h))
    if not bad:
        emit("PASS", "tmx-contracts", "%s: %d map(s) satisfy the Tiled contracts" % (plane, checked))


def tmx_tile_grid(path, layer_name):
    """(width, height, [gid]) for one base64+zlib tile layer, or (0, 0, [])."""
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return 0, 0, []
    m = re.search(r'\bwidth="(\d+)" height="(\d+)" tilewidth=', text)
    if not m:
        return 0, 0, []
    w, h = int(m.group(1)), int(m.group(2))
    lm = re.search(r'<layer[^>]*name="%s"[^>]*>(?:\s*<properties>.*?</properties>)?'
                   r'\s*<data encoding="base64" compression="zlib">(.*?)</data>'
                   % re.escape(layer_name), text, re.S)
    if not lm:
        return w, h, []
    try:
        raw = zlib.decompress(base64.b64decode(lm.group(1).strip()))
    except (ValueError, zlib.error):
        return w, h, []
    gids = [int.from_bytes(raw[i * 4:i * 4 + 4], "little") for i in range(w * h)]
    return w, h, gids


def check_entry_spawns(plane):
    """Where each `entry` object actually drops the player, and whether a
    dungeon can be left again.

    `direction` names the side the entry FACES; the player is placed on the
    OPPOSITE side. EntryActor.spawn() is explicit - "left" does
    setPosition(x + w, ...) and "right" does setPosition(x - playerWidth, ...).
    The shipped Adventure doc says the reverse ("up means the player will be
    teleported to the upper edge"), so reading the doc rather than the bytecode
    puts the player one tile the wrong way, which at a map edge means inside
    the border wall: alive, rendered, and unable to move.
    """
    # Player lands on the side OPPOSITE the one `direction` names.
    OFFSET = {"left": (1, 0), "right": (-1, 0), "up": (0, -1), "down": (0, 1)}
    bad = checked = 0
    for path in tmx_files(plane):
        rel = os.path.relpath(path, C.REPO).replace("\\", "/")
        w, h, ground = tmx_tile_grid(path, "Ground")
        try:
            with io.open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        exits = 0
        for om in re.finditer(r'<object id="(\d+)"[^>]*template="([^"]*)"[^>]*'
                              r'x="([\d.]+)" y="([\d.]+)"[^>]*>(.*?)</object>',
                              text, re.S):
            oid, tpl, x, y, body = om.groups()
            if "entry" not in tpl:
                continue
            checked += 1
            dm = re.search(r'<property name="direction"[^>]*value="([^"]*)"', body)
            direction = dm.group(1) if dm else ""
            tm = re.search(r'<property name="teleport"[^>]*value="([^"]*)"', body)
            if not (tm.group(1).strip() if tm else ""):
                exits += 1
            if not ground:
                continue
            dx, dy = OFFSET.get(direction, (0, 0))
            col = int(float(x) // 16) + dx
            row = int(float(y) // 16) - 1 + dy
            if not (0 <= col < w and 0 <= row < h):
                bad += 1
                emit("FAIL", "entry-spawn",
                     "%s: entry %s spawns the player outside the map at (%d,%d)"
                     % (rel, oid, col, row))
            elif ground[row * w + col]:
                bad += 1
                emit("FAIL", "entry-spawn",
                     "%s: entry %s (direction=%r) spawns the player into a solid tile "
                     "at (%d,%d) - they arrive stuck inside the wall"
                     % (rel, oid, direction, col, row))
        if exits == 0 and rel.endswith("_f1.tmx"):
            bad += 1
            emit("FAIL", "entry-spawn",
                 "%s: no entry with an empty teleport - the player cannot leave "
                 "the dungeon" % rel)
    if not bad:
        emit("PASS", "entry-spawn",
             "%s: %d entry object(s) land the player on open ground" % (plane, checked))


def tileset_collision(plane, tmx_path):
    """{local tile id -> True} for tiles that carry collision shapes, keyed by
    the GID offset the map declares. Returns {} when the tileset cannot be read."""
    try:
        with io.open(tmx_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return {}
    out = {}
    for firstgid, src in re.findall(r'<tileset firstgid="(\d+)" source="([^"]*)"', text):
        trimmed = src
        while trimmed.startswith("../"):
            trimmed = trimmed[3:]
        path = adventure_path(plane, "../" + trimmed)
        if not path:
            continue
        try:
            with io.open(path, encoding="utf-8", errors="replace") as f:
                tsx = f.read()
        except OSError:
            continue
        base = int(firstgid)
        for m in re.finditer(r'<tile id="(\d+)"[^>]*>(.*?)</tile>', tsx, re.S):
            out[base + int(m.group(1))] = "<objectgroup" in m.group(2)
    return out


def check_tile_collision(plane):
    """Floors must not collide and walls must.

    Both mistakes are invisible until you walk into them: a colliding tile in
    the Background layer seals a room the linter otherwise calls perfect, and a
    collision-free tile in the Ground layer is a wall you can stroll through.
    MapStage calls loadCollision() on EVERY tile layer, so which layer a tile is
    in decides nothing - only its shapes in the tileset do.
    """
    bad = checked = 0
    for path in tmx_files(plane):
        rel = os.path.relpath(path, C.REPO).replace("\\", "/")
        collides = tileset_collision(plane, path)
        if not collides:
            emit("BLOCKED", "tile-collision", "%s: tileset not resolvable" % rel)
            return
        for layer, want in (("Background", False), ("Ground", True)):
            w, _h, gids = tmx_tile_grid(path, layer)
            if not gids:
                continue
            for gid in sorted({g for g in gids if g}):
                checked += 1
                if collides.get(gid, False) != want:
                    bad += 1
                    emit("FAIL", "tile-collision",
                         "%s: %s layer uses gid %d which %s collision - a %s tile "
                         "there %s" % (rel, layer, gid,
                                       "has" if not want else "has no",
                                       "solid" if not want else "walkable",
                                       "seals the room" if not want
                                       else "is a wall you can walk through"))
    if not bad:
        emit("PASS", "tile-collision",
             "%s: %d distinct tile id(s) sit in the right layer" % (plane, checked))


def check_reachability(plane):
    """Every object on a floor must be walkable-to from where the player lands.

    Carving rooms and corridors procedurally makes it easy to seal one off by a
    tile. Forge will happily load that map; the roamer and its treasure simply
    never happen.
    """
    OFFSET = {"left": (1, 0), "right": (-1, 0), "up": (0, -1), "down": (0, 1)}
    bad = checked = 0
    for path in tmx_files(plane):
        rel = os.path.relpath(path, C.REPO).replace("\\", "/")
        w, h, ground = tmx_tile_grid(path, "Ground")
        if not ground:
            continue
        try:
            with io.open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        start, targets = None, []
        for om in re.finditer(r'<object id="(\d+)"[^>]*template="([^"]*)"[^>]*'
                              r'x="([\d.]+)" y="([\d.]+)"[^>]*?(?:/>|>(.*?)</object>)',
                              text, re.S):
            oid, tpl, x, y, body = om.group(1), om.group(2), om.group(3), om.group(4), om.group(5) or ""
            col, row = int(float(x) // 16), int(float(y) // 16) - 1
            if "entry" in tpl:
                dm = re.search(r'<property name="direction"[^>]*value="([^"]*)"', body)
                dx, dy = OFFSET.get(dm.group(1) if dm else "", (0, 0))
                tm = re.search(r'<property name="teleport"[^>]*value="([^"]*)"', body)
                if start is None or not (tm.group(1).strip() if tm else ""):
                    start = (col + dx, row + dy)
            targets.append((oid, os.path.basename(tpl), col, row))
        if start is None:
            continue
        seen = set()
        stack = [start]
        while stack:
            c, r = stack.pop()
            if (c, r) in seen or not (0 <= c < w and 0 <= r < h):
                continue
            if ground[r * w + c]:
                continue
            seen.add((c, r))
            stack += [(c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)]
        for oid, tpl, col, row in targets:
            checked += 1
            if (col, row) not in seen:
                bad += 1
                emit("FAIL", "map-reachability",
                     "%s: %s object %s at (%d,%d) cannot be walked to from the "
                     "player's landing cell" % (rel, tpl, oid, col, row))
    if not bad:
        emit("PASS", "map-reachability",
             "%s: %d map object(s) are reachable" % (plane, checked))


# forge.card.CardRarity, one of the engine's closed sets: an unrecognised name
# does not error, smartValueOf() returns Unknown and the filter then matches
# nothing, so the reward silently disappears.
FORGE_RARITIES = {"basicland", "basic land", "common", "uncommon", "rare",
                  "mythicrare", "mythic rare", "special", "token", "unknown"}


def check_reward_duplicates(plane):
    """Deck-card hauls must be unable to hand out the same card twice.

    CardUtil.generateCards() draws WITH REPLACEMENT - it loops `count` times
    over filtered.get(rand.nextInt(size)) and never removes what it drew - and
    there is no data field to change that. The only way to guarantee distinct
    cards is one draw per entry across mutually exclusive filters, so that is
    what this check enforces:

      * every `deckCard` entry draws exactly once (count 1, no addMaxCount), and
      * no two of an enemy's `deckCard` entries can match the same card, which
        means their rarity sets and mana-cost sets must not both overlap.

    It also rejects a rarity string CardRarity.smartValueOf() would not know,
    because that turns into Unknown and the reward quietly vanishes.
    """
    enemies, origin = load_plane_json(plane, "world/enemies.json")
    if enemies is None:
        emit("BLOCKED", "reward-no-duplicates", "%s: no enemies.json" % plane)
        return
    if origin != "plane":
        emit("PASS", "reward-no-duplicates", "%s: uses common's enemies unchanged" % plane)
        return
    bad = checked = 0
    for entry in enemies if isinstance(enemies, list) else []:
        entry = entry or {}
        name = entry.get("name", "?")
        buckets = []
        for rw in entry.get("rewards", []) or []:
            for rarity in (rw or {}).get("rarity", []) or []:
                if str(rarity).lower() not in FORGE_RARITIES:
                    bad += 1
                    emit("FAIL", "reward-no-duplicates",
                         "%s: enemy %r reward rarity %r is not a CardRarity - "
                         "smartValueOf returns Unknown and the reward vanishes"
                         % (plane, name, rarity))
            if (rw or {}).get("type") != "deckCard":
                continue
            checked += 1
            if rw.get("count", 1) != 1 or rw.get("addMaxCount"):
                bad += 1
                emit("FAIL", "reward-no-duplicates",
                     "%s: enemy %r has a deckCard entry drawing %d+%d times - the "
                     "engine draws with replacement, so it can repeat a card"
                     % (plane, name, rw.get("count", 1), rw.get("addMaxCount", 0)))
            buckets.append((frozenset(str(r).lower() for r in (rw.get("rarity") or [])),
                            frozenset(rw.get("manaCosts") or [])))
        for i in range(len(buckets)):
            for j in range(i + 1, len(buckets)):
                (r1, m1), (r2, m2) = buckets[i], buckets[j]
                r_overlap = (not r1) or (not r2) or (r1 & r2)
                m_overlap = (not m1) or (not m2) or (m1 & m2)
                if r_overlap and m_overlap:
                    bad += 1
                    emit("FAIL", "reward-no-duplicates",
                         "%s: enemy %r has two deckCard buckets that can match the "
                         "same card (rarity %s vs %s, cmc %s vs %s)"
                         % (plane, name, sorted(r1) or "any", sorted(r2) or "any",
                            sorted(m1) or "any", sorted(m2) or "any"))
    if not bad:
        emit("PASS", "reward-no-duplicates",
             "%s: %d deck-card bucket(s) are single-draw and mutually exclusive"
             % (plane, checked))


def check_biome_enemies(plane):
    """A biome must OMIT `enemies` rather than set it to [].

    BiomeData.getEnemyList() copies EVERY enemy in enemies.json into the biome's
    list with spawnRate forced to 0, and only the names in `enemies` keep their
    real rate. BiomeData.getEnemy(rank) then filters by difficulty <= rank and,
    when that filter comes up empty, falls back to Aggregates.random over the
    WHOLE list - ignoring spawnRate entirely. So `"enemies": []` does not mean
    "no overworld enemies", it means "spawn any enemy in the plane, including
    the ones marked spawnRate 0".

    Omitting the key leaves the field null, which makes getEnemyList() return
    an empty list, Aggregates.random return null, and WorldStage.spawn(null)
    return false without spawning.
    """
    world, _ = load_plane_json(plane, "world/world.json")
    if world is None:
        emit("BLOCKED", "biome-enemy-list", "%s: no world.json" % plane)
        return
    bad = checked = 0
    for biome_rel in (world.get("biomesNames") or []):
        path, origin = plane_file(plane, biome_rel)
        if origin != "plane":
            continue
        checked += 1
        try:
            with io.open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            continue
        if "enemies" in raw and not raw["enemies"]:
            bad += 1
            emit("FAIL", "biome-enemy-list",
                 "%s: %s sets \"enemies\": [] - that spawns ANY enemy in the plane, "
                 "spawnRate 0 included. Remove the key entirely for no overworld "
                 "enemies." % (plane, biome_rel))
    if not bad:
        emit("PASS", "biome-enemy-list",
             "%s: %d plane-owned biome(s) declare their enemies safely" % (plane, checked))


def check_enemy_decks(plane):
    """Every deck path an enemy names resolves."""
    enemies, _ = load_plane_json(plane, "world/enemies.json")
    if enemies is None:
        emit("BLOCKED", "enemy-deck-resolve", "%s: no enemies.json in plane or common" % plane)
        return
    bad = checked = 0
    for entry in enemies if isinstance(enemies, list) else []:
        for deck in (entry or {}).get("deck", []) or []:
            checked += 1
            if not adventure_path(plane, deck):
                bad += 1
                emit("FAIL", "enemy-deck-resolve",
                     "%s: enemy %r deck %r does not resolve"
                     % (plane, entry.get("name", "?"), deck))
    if not bad:
        emit("PASS", "enemy-deck-resolve", "%s: %d deck path(s) resolve" % (plane, checked))


def check_poi_wiring(plane):
    """POI maps and sprites resolve, and every POI is named by some biome.

    A POI no biome lists is authored content the player can never reach, and
    nothing in Forge says so.
    """
    pois, origin = load_plane_json(plane, "world/points_of_interest.json")
    if pois is None:
        emit("BLOCKED", "poi-wiring", "%s: no points_of_interest.json" % plane)
        return
    if origin != "plane":
        emit("PASS", "poi-wiring", "%s: uses common's POIs unchanged" % plane)
        return
    bad = 0
    names = set()
    for poi in pois if isinstance(pois, list) else []:
        poi = poi or {}
        names.add(poi.get("name"))
        if not adventure_path(plane, poi.get("map")):
            bad += 1
            emit("FAIL", "poi-wiring", "%s: POI %r map %r does not resolve"
                 % (plane, poi.get("name"), poi.get("map")))
        atlas = adventure_path(plane, poi.get("spriteAtlas"))
        if not atlas:
            bad += 1
            emit("FAIL", "poi-wiring", "%s: POI %r spriteAtlas %r does not resolve"
                 % (plane, poi.get("name"), poi.get("spriteAtlas")))
        elif poi.get("sprite") and poi["sprite"] not in atlas_regions(atlas):
            bad += 1
            emit("FAIL", "poi-wiring", "%s: POI %r sprite region %r is not in %s"
                 % (plane, poi.get("name"), poi["sprite"], os.path.basename(atlas)))

    world, _ = load_plane_json(plane, "world/world.json")
    listed = set()
    for biome_rel in ((world or {}).get("biomesNames") or []):
        biome, _o = load_plane_json(plane, biome_rel)
        for n in ((biome or {}).get("pointsOfInterest") or []):
            listed.add(n)
    for orphan in sorted(n for n in names - listed if n):
        bad += 1
        emit("FAIL", "poi-wiring",
             "%s: POI %r is in no biome's pointsOfInterest - it is never placed"
             % (plane, orphan))
    for ghost in sorted(n for n in listed - names if n):
        bad += 1
        emit("FAIL", "poi-wiring",
             "%s: a biome lists POI %r which points_of_interest.json does not define"
             % (plane, ghost))
    if not bad:
        emit("PASS", "poi-wiring", "%s: %d POI(s) resolve and are placed" % (plane, len(names)))


def check_commander_decks(plane):
    """A .dck with a [Commander] section must be a legal 100-card deck.

    Adventure applies its deck rules to the PLAYER's deck only - the enemy's
    deck is registered exactly as written. A 99-card 'commander' deck therefore
    never errors, it just quietly plays one card short forever.
    """
    deck_root = os.path.join(C.REPO, "planes", plane, "decks")
    if not os.path.isdir(deck_root):
        emit("PASS", "commander-deck-size", "%s: no plane-local decks" % plane)
        return
    bad = checked = 0
    for dirpath, _d, filenames in os.walk(deck_root):
        for fn in sorted(filenames):
            if not fn.endswith(".dck"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, C.REPO)
            counts = {}
            section_name = None
            try:
                with io.open(path, encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()
            except OSError:
                continue
            for line in lines:
                s = line.strip()
                if s.startswith("["):
                    section_name = s.lower().strip("[]")
                    counts.setdefault(section_name, 0)
                    continue
                m = re.match(r"^(\d+)\s+(.+)$", s)
                if m and section_name in ("main", "commander"):
                    counts[section_name] = counts.get(section_name, 0) + int(m.group(1))
            if "commander" not in counts:
                continue
            checked += 1
            total = counts.get("main", 0) + counts.get("commander", 0)
            if total != 100:
                bad += 1
                emit("FAIL", "commander-deck-size",
                     "%s: %d cards in Main+Commander, needs exactly 100" % (rel, total))
            elif not 1 <= counts["commander"] <= 2:
                bad += 1
                emit("FAIL", "commander-deck-size",
                     "%s: %d commander(s), expected 1 or 2" % (rel, counts["commander"]))
    if not bad:
        emit("PASS", "commander-deck-size",
             "%s: %d commander deck(s) are legal 100-card decks" % (plane, checked))


# Checks named in the architecture but not implemented yet. Listed every run.
TODO_CHECKS = [
    ("quest-reference-resolve",
     "quests.json objectives/dialog actions against the closed enum sets"),
    ("edition-coverage",
     "every card under custom/cards/ has an entry in a custom/editions/ file - "
     "a script with no edition entry is silently skipped"),
    ("name-collision",
     "custom card names against real MTG card names - a collision silently "
     "resolves to the real card"),
]


def main():
    print("ForgeModding verify report")
    print("=" * 26)
    root = C.install_root()
    print("repo:          %s" % C.REPO)
    print("forge install: %s" % (root or "(unbound)"))
    print("install build: %s" % (C.install_build_txt() or "(unknown)"))
    print("planes:        %s" % (", ".join(C.planes()) or "(none authored yet)"))

    section("Machine prerequisites")
    check_prereqs()

    section("Content")
    check_json_parses()
    for plane in C.planes():
        check_sprites(plane)
        check_decks(plane)
        check_commander_decks(plane)
        check_enemy_decks(plane)
        check_map_enemies(plane)
        check_map_links(plane)
        check_tmx_contracts(plane)
        check_biome_enemies(plane)
        check_entry_spawns(plane)
        check_tile_collision(plane)
        check_reachability(plane)
        check_reward_duplicates(plane)
        check_poi_wiring(plane)
        check_items(plane)
        check_battle_cards(plane)
        check_ownership(plane)
    if not C.planes():
        emit("PASS", "content", "no planes authored yet - nothing to lint")

    section("Engine track")
    check_engine()

    section("Not implemented yet")
    for name, what in TODO_CHECKS:
        print("%-8s %-26s %s" % ("TODO", name, what))

    fails = sum(1 for s, _c, _d in RESULTS if s == "FAIL")
    blocked = sum(1 for s, _c, _d in RESULTS if s == "BLOCKED")
    passed = sum(1 for s, _c, _d in RESULTS if s == "PASS")
    section("Summary")
    print("PASS %d   FAIL %d   BLOCKED %d   TODO %d" % (passed, fails, blocked, len(TODO_CHECKS)))
    if blocked:
        print("\nBLOCKED checks did not run. They are machine gaps, not content defects -")
        print("but this report does NOT certify what they would have covered.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
