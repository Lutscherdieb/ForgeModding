# -*- coding: utf-8 -*-
"""Shared path resolution for the ForgeModding tools.

WHAT THIS IS: the single place that answers "where is the Forge install?",
"where is the engine workspace?", "where is the repo root?". Every other script
in tools/ imports from here rather than re-deriving paths, so a machine that
binds its references once is bound for all of them.

WHY IT READS references.local.json: the four read-only references declared in
REFERENCES.md are bound per-machine in that gitignored file (repo root, exactly
there - the ClaudeBase hooks look nowhere else). The install root is derived
from the forge-common binding rather than asked for separately, so there is one
source of truth per machine instead of two that can disagree.

NOTHING HERE WRITES. Deploy and engine scripts do their own writing.
"""
import json
import os
import shutil

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def bindings():
    """The machine-local reference bindings, or {} when unbound."""
    return _load_json(os.path.join(REPO, "references.local.json"))


def ref(ref_id):
    """Absolute path bound to a declared reference id, or None."""
    p = bindings().get(ref_id)
    return os.path.normpath(p) if p else None


def install_root():
    """The Forge install root, derived from the forge-common binding.

    forge-common is bound to <install>/res/adventure/common, so the install is
    three levels up. Deriving beats asking: one binding cannot drift from
    another that does not exist.
    """
    common = ref("forge-common")
    if not common:
        return None
    return os.path.normpath(os.path.join(common, "..", "..", ".."))


def install_build_txt():
    """The install's build.txt contents, or None. This is the 'which upstream
    build am I forked from' value that OWNERSHIP.md rows must carry."""
    root = install_root()
    if not root:
        return None
    try:
        with open(os.path.join(root, "build.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def workspace():
    """The engine workspace clone path, or None when not bootstrapped."""
    cfg = _load_json(os.path.join(REPO, "engine", "workspace.local.json"))
    p = cfg.get("workspace")
    return os.path.normpath(p) if p else None


def planes():
    """Plane directory names under planes/, in sorted order."""
    root = os.path.join(REPO, "planes")
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)) and not d.startswith("."))


def tool_available(name):
    """True when an executable is on PATH. Used to report BLOCKED rather than
    to fail: a missing tool is a machine gap, not a content error."""
    return shutil.which(name) is not None
