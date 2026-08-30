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
import io
import json
import os
import re
import subprocess
import sys
import zipfile

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
    items, _ = load_plane_json(plane, "world/items.json")
    enemies, _ = load_plane_json(plane, "world/enemies.json")
    if items is None:
        emit("BLOCKED", "equipment-resolve", "%s: no items.json in plane or common" % plane)
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
    items, _ = load_plane_json(plane, "world/items.json")
    if items is None:
        emit("BLOCKED", "battle-card-resolve", "%s: no items.json" % plane)
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
            ledger = f.read()
    except OSError:
        emit("FAIL", "ownership-ledger", "OWNERSHIP.md is missing")
        return
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


# Checks named in the architecture but not implemented yet. Listed every run.
TODO_CHECKS = [
    ("quest-reference-resolve",
     "quests.json objectives/dialog actions against the closed enum sets"),
    ("poi-map-resolve",
     "points_of_interest.json entries against the .tmx maps they name"),
    ("tmx-constraints",
     "Tiled hard constraints: 16x16 tiles, exactly ONE object layer, a tile layer "
     "carrying spriteLayer=true, <=6 tile layers, CSV format"),
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
