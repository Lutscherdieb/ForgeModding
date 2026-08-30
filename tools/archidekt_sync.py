# -*- coding: utf-8 -*-
"""Fetch an Archidekt user's public Commander decks and emit Adventure decks.

WHAT THIS IS: the front half of the Archidekt Vaults pipeline. It reads one or
more Archidekt usernames, keeps only the decks that are legal as Adventure
roaming opponents, writes them as Forge *.dck files, and records every deck it
saw - kept or rejected, and why - in a roster manifest that tools/gen_vault.py
turns into enemies, maps and treasure.

    python tools/archidekt_sync.py Lutscherdieb
    python tools/archidekt_sync.py Lutscherdieb --refresh     # re-download
    python tools/archidekt_sync.py Lutscherdieb --offline     # cache only

THE LEGALITY GATE, and why it is written the way it is:

  A deck is kept when, after removing every card whose category is excluded, it
  is EXACTLY 100 cards and has 1-2 commanders.

  "Excluded" means: any category with includedInDeck=false, PLUS the category
  literally named "Sideboard". That second clause is not optional. Archidekt
  ships "Sideboard" with includedInDeck=TRUE, so dropping only the non-included
  categories leaves most Commander decks at 103-133 cards and the gate rejects
  decks that are actually fine. Measured on 37 decks: excluding non-included
  categories alone passes 2; adding the Sideboard clause passes 21.

  Do NOT also exclude "Tokens" or "Tokens & Extras" by name. Those are real
  theme categories in some decks - excluding "Tokens" by name takes a legal
  100-card deck down to 86 and silently drops it from the vault.

THE POWER SCORE, and why edhBracket is not it:

  Archidekt exposes deck.edhBracket, but it is only set when the owner set it
  by hand - 14 of 21 legal decks measured had it null. So the bracket is
  RECONSTRUCTED from the same per-card signals the official bracket rules use,
  all of which Archidekt returns on every card: gameChanger, tutor, extraTurns,
  massLandDenial and two-card combo membership. That proxy is blended 50/50
  with the deck's retail value, per the project's chosen weighting.

  Both halves use FIXED anchors, not min/max over the current roster. A
  roster-relative score would silently re-tier and re-price every existing
  roamer the moment one deck is added or fixed.

NOTHING HERE WRITES OUTSIDE planes/<plane>/decks/ AND THE CACHE. It never
touches the Forge install; tools/deploy.py is the only path in.
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

API = "https://archidekt.com/api"
UA = "ForgeModding-archidekt-sync/1.0 (+local adventure content tool)"
CACHE = os.path.join(C.REPO, ".archidekt-cache")

# Archidekt deckFormat id for Commander. Anything else is not a vault candidate.
FORMAT_COMMANDER = 3

# Categories excluded from the maindeck count. See the module docstring - the
# "Sideboard" clause is load-bearing and the token clause is deliberately absent.
EXCLUDE_BY_NAME = {"Sideboard"}

# Fixed score anchors. bp is the reconstructed bracket proxy; price is retail
# USD across the 100 cards. Observed ranges over one real 21-deck roster were
# bp 0.5-25.5 and price 465-1328, which is what these anchors are set against.
BP_ANCHOR = 25.0
PRICE_FLOOR = 400.0
PRICE_SPAN = 1000.0

# Bracket-proxy weights, mirroring what the official Commander bracket rules
# actually care about. Extra turns and mass land denial are rated highest
# because they are the two things that end an Adventure duel unanswerably.
W_GAME_CHANGER = 3.0
W_TUTOR = 1.5
W_EXTRA_TURNS = 4.0
W_MASS_LAND_DENIAL = 4.0
W_COMBO = 0.5


def slugify(text):
    """A stable, filesystem- and Forge-safe deck slug.

    Forge resolves deck paths verbatim out of JSON, and Adventure content is
    copied across PC and Android, so anything but [a-z0-9_] is a portability
    bet not worth taking.
    """
    s = text.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return re.sub(r"_+", "_", s) or "deck"


def _get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_deck_list(user):
    """Every public deck owned by `user`.

    The filter parameter is ownerUsername. `owner` is silently IGNORED by the
    API - it returns the global recent-decks feed with a 200, so a typo there
    does not error, it quietly imports strangers' decks. The owner assertion
    below is what makes that failure loud instead of silent.
    """
    out, page = [], 1
    while True:
        d = _get("%s/decks/v3/?ownerUsername=%s&pageSize=100&page=%d" % (API, user, page))
        got = d.get("results") or []
        for x in got:
            owner = (x.get("owner") or {}).get("username")
            if owner != user:
                raise SystemExit(
                    "ABORT: Archidekt returned a deck owned by %r while asking for %r. "
                    "The owner filter is not being applied; refusing to import."
                    % (owner, user))
        out.extend(got)
        if not d.get("next"):
            return out
        page += 1


def fetch_deck(deck_id, refresh=False, offline=False):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "%s.json" % deck_id)
    if not refresh and os.path.exists(path) and os.path.getsize(path) > 1000:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    if offline:
        return None
    d = _get("%s/decks/%s/" % (API, deck_id))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f)
    return d


def split_deck(d):
    """(maindeck cards, commander cards) after applying the exclusion rule."""
    excluded = set()
    premier = set()
    for c in d.get("categories", []):
        if not c.get("includedInDeck"):
            excluded.add(c["name"])
        if c.get("isPremier"):
            premier.add(c["name"])
    excluded |= EXCLUDE_BY_NAME
    main, commanders = [], []
    for c in d.get("cards", []):
        cats = set(c.get("categories") or [])
        if cats & excluded:
            continue
        if (cats & premier) or "Commander" in cats:
            commanders.append(c)
        else:
            main.append(c)
    return main, commanders


def score_deck(cards):
    """Bracket proxy, retail value, and the blended 0..1 score."""
    gc = tut = ext = mld = 0
    price = 0.0
    combos = set()
    for c in cards:
        q = c.get("quantity", 1)
        o = c["card"].get("oracleCard") or {}
        pr = c["card"].get("prices") or {}
        gc += q * bool(o.get("gameChanger"))
        tut += q * bool(o.get("tutor"))
        ext += q * bool(o.get("extraTurns"))
        mld += q * bool(o.get("massLandDenial"))
        price += q * (pr.get("tcg") or pr.get("ck") or pr.get("cm") or 0)
        for cid in (o.get("twoCardComboIds") or []):
            combos.add(cid)
    bp = (W_GAME_CHANGER * gc + W_TUTOR * tut + W_EXTRA_TURNS * ext
          + W_MASS_LAND_DENIAL * mld + W_COMBO * len(combos))
    n_bp = min(1.0, bp / BP_ANCHOR)
    n_pr = min(1.0, max(0.0, (price - PRICE_FLOOR) / PRICE_SPAN))
    return {
        "bracketProxy": round(bp, 1),
        "gameChangers": gc,
        "tutors": tut,
        "extraTurns": ext,
        "massLandDenial": mld,
        "combos": len(combos),
        "priceUsd": round(price),
        "score": round(0.5 * n_bp + 0.5 * n_pr, 3),
    }


# Archidekt spells colour identity out in full ("Black"), not as WUBRG letters,
# while Forge's enemy `colors` field wants the letters. Mapping in one place
# beats discovering "C" on every enemy after a playtest.
ARCHIDEKT_COLORS = {"White": "W", "Blue": "U", "Black": "B", "Red": "R", "Green": "G"}


def deck_colors(cards):
    """WUBRG identity letters present in the deck, in canonical order."""
    seen = set()
    for c in cards:
        for name in ((c["card"].get("oracleCard") or {}).get("colorIdentity") or []):
            letter = ARCHIDEKT_COLORS.get(name)
            if letter:
                seen.add(letter)
    letters = [ch for ch in "WUBRG" if ch in seen]
    return "".join(letters) or "C"


def forge_card_names():
    """Every card name Forge knows, from the declared read-only card corpus.

    Read-only: this opens cardsfolder.zip and never writes near it. A card name
    Forge does not know is dropped SILENTLY at deck load, which is why an
    unresolvable name rejects the whole deck here instead of shipping a
    99-card 'commander' deck that looks fine in the file.
    """
    corpus = C.ref("forge-card-corpus")
    if not corpus:
        raise SystemExit("BLOCKED: forge-card-corpus is not bound in "
                         "references.local.json (run /base:repo-setup).")
    names = set()
    zpath = os.path.join(corpus, "cardsfolder.zip")
    if os.path.exists(zpath):
        with zipfile.ZipFile(zpath) as z:
            for info in z.infolist():
                if not info.filename.endswith(".txt"):
                    continue
                with z.open(info) as f:
                    for line in io.TextIOWrapper(f, encoding="utf-8", errors="ignore"):
                        if line.startswith("Name:"):
                            names.add(line[5:].strip())
                            break
    for root, _, files in os.walk(corpus):
        for fn in files:
            if not fn.endswith(".txt"):
                continue
            try:
                with open(os.path.join(root, fn), encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.startswith("Name:"):
                            names.add(line[5:].strip())
                            break
            except OSError:
                pass
    if not names:
        raise SystemExit("BLOCKED: no card names found under %s" % corpus)
    return names


def forge_edition_codes():
    """Set codes Forge knows. An unknown code is written as a bare card name so
    Forge picks any printing, rather than as a set pin it cannot resolve."""
    codes = set()
    root = C.install_root()
    if not root:
        return codes
    ed = os.path.join(root, "res", "editions")
    if not os.path.isdir(ed):
        return codes
    for fn in os.listdir(ed):
        if not fn.endswith(".txt"):
            continue
        try:
            with open(os.path.join(ed, fn), encoding="utf-8", errors="ignore") as f:
                for line in f:
                    m = re.match(r"\s*Code\s*=\s*(\S+)", line)
                    if m:
                        codes.add(m.group(1).upper())
                        break
        except OSError:
            pass
    return codes


def resolve_name(card, known):
    """The name Forge will match, or None. Handles Archidekt's double-faced
    naming by falling back to the front face."""
    nm = (card["card"].get("oracleCard") or {}).get("name") or ""
    if nm in known:
        return nm
    front = nm.split(" // ")[0].strip()
    if front in known:
        return front
    return None


def dck_line(card, known, codes):
    name = resolve_name(card, known)
    if name is None:
        return None
    ed = ((card["card"].get("edition") or {}).get("editioncode") or "").upper()
    q = card.get("quantity", 1)
    if ed and ed in codes:
        return "%d %s|%s" % (q, name, ed)
    return "%d %s" % (q, name)


def write_dck(path, deck_name, url, commanders, main, known, codes):
    lines = ["[metadata]", "Name=%s" % deck_name, "Deck Type=Commander"]
    if url:
        lines.append("Source URL=%s" % url)
    lines.append("[Commander]")
    for c in commanders:
        lines.append(dck_line(c, known, codes))
    lines.append("[Main]")
    ordered = sorted(main, key=lambda x: ((x["card"].get("oracleCard") or {}).get("name") or ""))
    for c in ordered:
        lines.append(dck_line(c, known, codes))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def sync_user(user, plane, refresh, offline):
    known = forge_card_names()
    codes = forge_edition_codes()
    user_slug = slugify(user)
    deck_dir = os.path.join(C.REPO, "planes", plane, "decks", user_slug)

    listing = fetch_deck_list(user)
    print("archidekt: %s has %d public deck(s)" % (user, len(listing)))
    entries, kept = [], 0

    for meta in sorted(listing, key=lambda x: x["name"].lower()):
        row = {
            "id": meta["id"],
            "name": meta["name"],
            "listedSize": meta.get("size"),
            "url": "https://archidekt.com/decks/%s" % meta["id"],
            "kept": False,
            "reason": None,
        }
        if meta.get("deckFormat") != FORMAT_COMMANDER:
            row["reason"] = "not a Commander deck (deckFormat=%s)" % meta.get("deckFormat")
            entries.append(row)
            continue
        d = fetch_deck(meta["id"], refresh=refresh, offline=offline)
        if d is None:
            row["reason"] = "not in cache and --offline was given"
            entries.append(row)
            continue
        main, commanders = split_deck(d)
        total = sum(c.get("quantity", 1) for c in main + commanders)
        row["deckSize"] = total
        row["commanders"] = [(c["card"].get("oracleCard") or {}).get("name")
                             for c in commanders]
        # The commander's creature types drive both the roamer's sprite and its
        # room theme downstream, so they are recorded here rather than making
        # gen_vault.py re-open the raw Archidekt cache.
        types = []
        for c in commanders:
            o = c["card"].get("oracleCard") or {}
            types += list(o.get("subTypes") or []) + list(o.get("types") or [])
        row["commanderTypes"] = sorted(set(types))
        if not commanders:
            row["reason"] = "no commander marked on Archidekt"
        elif len(commanders) > 2:
            row["reason"] = "%d commanders (max 2, for partners)" % len(commanders)
        elif total != 100:
            row["reason"] = "%d cards, needs exactly 100" % total
        if row["reason"] is None:
            unknown = sorted({(c["card"].get("oracleCard") or {}).get("name")
                              for c in main + commanders
                              if resolve_name(c, known) is None})
            if unknown:
                row["reason"] = ("card name(s) Forge does not know: %s"
                                 % ", ".join(unknown[:4]))
        if row["reason"] is not None:
            entries.append(row)
            continue

        slug = slugify(meta["name"])
        row.update(score_deck(main + commanders))
        row["kept"] = True
        row["slug"] = slug
        row["colors"] = deck_colors(main + commanders)
        row["deckPath"] = "decks/%s/%s.dck" % (user_slug, slug)
        write_dck(os.path.join(deck_dir, slug + ".dck"), meta["name"], row["url"],
                  commanders, main, known, codes)
        entries.append(row)
        kept += 1

    entries.sort(key=lambda r: (not r["kept"], -(r.get("score") or 0), r["name"].lower()))
    roster = {
        "user": user,
        "userSlug": user_slug,
        "plane": plane,
        "syncedAt": time.strftime("%Y-%m-%d"),
        "kept": kept,
        "seen": len(entries),
        "gate": ("maindeck excludes includedInDeck=false categories plus 'Sideboard'; "
                 "must be exactly 100 cards with 1-2 commanders and every card name "
                 "known to Forge"),
        "decks": entries,
    }
    os.makedirs(deck_dir, exist_ok=True)
    with open(os.path.join(deck_dir, "_roster.json"), "w", encoding="utf-8",
              newline="\n") as f:
        json.dump(roster, f, indent=2)
        f.write("\n")

    # A .dck left over from an earlier sync, whose deck no longer qualifies,
    # would otherwise linger as an orphan the generator never references.
    live = {"%s.dck" % r["slug"] for r in entries if r["kept"]}
    for fn in sorted(os.listdir(deck_dir)):
        if fn.endswith(".dck") and fn not in live:
            os.remove(os.path.join(deck_dir, fn))
            print("  removed stale deck %s" % fn)

    print("  kept %d of %d as vault roamers" % (kept, len(entries)))
    for r in entries:
        if not r["kept"]:
            print("  skip  %-46s %s" % (r["name"][:46], r["reason"]))
    return roster


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("users", nargs="+", help="Archidekt username(s)")
    ap.add_argument("--plane", default="Archidekt_Vaults")
    ap.add_argument("--refresh", action="store_true", help="re-download cached decks")
    ap.add_argument("--offline", action="store_true", help="use only the local cache")
    a = ap.parse_args()
    for u in a.users:
        sync_user(u, a.plane, a.refresh, a.offline)
    print("\nnext: python tools/gen_vault.py")


if __name__ == "__main__":
    main()
