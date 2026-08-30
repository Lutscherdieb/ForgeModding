# -*- coding: utf-8 -*-
"""Export the workspace's forgemodding branch back into engine/patches/.

    python tools/engine_export.py

This is the ONLY engine script that writes into this repo. Everything committed
on `forgemodding` above the merge base becomes a numbered .patch file, and the
previous series is replaced wholesale so a rebase or a squash upstream cannot
leave orphaned patch files behind.

After exporting, update engine/PINNED.md: every patch needs the closed set it
extends, the content type it unlocks, the data-layer approach that was tried
first and why it failed, and what under planes/ or custom/ actually consumes it.
A patch no content consumes does not ship.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402


def main():
    ws = C.workspace()
    if not ws or not os.path.isdir(ws):
        print("BLOCKED: no engine workspace. Run tools/engine_bootstrap.py first.")
        return 2

    cfg_path = os.path.join(C.REPO, "engine", "workspace.local.json")
    try:
        with open(cfg_path, encoding="utf-8") as f:
            branch = json.load(f).get("branch", "forgemodding")
    except (OSError, ValueError):
        branch = "forgemodding"

    base_r = subprocess.run(["git", "-C", ws, "merge-base", branch, "origin/HEAD"],
                            capture_output=True, text=True)
    if base_r.returncode != 0:
        print("Could not find the merge base against origin/HEAD:")
        print(base_r.stderr.strip())
        return 1
    base = base_r.stdout.strip()

    patch_dir = os.path.join(C.REPO, "engine", "patches")
    os.makedirs(patch_dir, exist_ok=True)
    for old in os.listdir(patch_dir):
        if old.endswith(".patch"):
            os.remove(os.path.join(patch_dir, old))

    r = subprocess.run(["git", "-C", ws, "format-patch", "-o", patch_dir,
                        "%s..%s" % (base, branch)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr.strip())
        return 1
    written = [line for line in r.stdout.splitlines() if line.strip()]
    print("Exported %d patch(es) from %s..%s" % (len(written), base[:12], branch))
    for line in written:
        print("  " + os.path.basename(line))
    print("")
    print("NOW UPDATE engine/PINNED.md - per patch: the closed set extended, the content")
    print("type unlocked, the data-layer approach tried first and why it failed, and what")
    print("consumes it. Then update OWNERSHIP.md's engine-pin row.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
