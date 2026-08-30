# -*- coding: utf-8 -*-
"""Apply engine/patches/*.patch onto the pinned commit in the workspace.

    python tools/engine_apply.py            # reset to pin, apply the series
    python tools/engine_apply.py --check    # dry run: would they apply?

Replays the series in filename order onto the `forgemodding` branch. Commit any
work-in-progress in the workspace first - this replays history, and uncommitted
changes in the way will stop it.

After an upstream bump this is where the real cost of the engine track shows up:
conflicts get resolved here, then re-exported with engine_export.py, and the
conflict gets a line in engine/PINNED.md's re-apply log.
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="dry run, change nothing")
    args = ap.parse_args()

    ws = C.workspace()
    if not ws or not os.path.isdir(ws):
        print("BLOCKED: no engine workspace. Run tools/engine_bootstrap.py first.")
        return 2

    patch_dir = os.path.join(C.REPO, "engine", "patches")
    patches = sorted(f for f in os.listdir(patch_dir)) if os.path.isdir(patch_dir) else []
    patches = [os.path.join(patch_dir, p) for p in patches if p.endswith(".patch")]
    if not patches:
        print("No patches in the series - nothing to apply.")
        return 0

    if args.check:
        r = subprocess.run(["git", "-C", ws, "apply", "--check"] + patches,
                           capture_output=True, text=True)
        print("would apply cleanly" if r.returncode == 0 else r.stderr.strip())
        return r.returncode

    r = subprocess.run(["git", "-C", ws, "am", "--3way"] + patches,
                       capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr.strip())
        print("")
        print("CONFLICT. Resolve in the workspace, then `git am --continue`.")
        print("Record it in engine/PINNED.md's re-apply log - that log is what makes")
        print("the true cost of this track visible instead of merely felt.")
        return 1
    print("Applied %d patch(es) onto the pin." % len(patches))
    return 0


if __name__ == "__main__":
    sys.exit(main())
