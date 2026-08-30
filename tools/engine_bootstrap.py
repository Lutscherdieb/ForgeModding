# -*- coding: utf-8 -*-
"""Bootstrap the engine workspace: prereq check, clone, pin, branch.

    python tools/engine_bootstrap.py --workspace "E:\\Projekte\\forge-src"
    python tools/engine_bootstrap.py --check      # prereqs only, clone nothing

WHAT IT CREATES: a Forge clone OUTSIDE this repo, on a `forgemodding` branch cut
from a pinned upstream commit, and gitignored engine/workspace.local.json
pointing at it. The clone is disposable - it can always be recreated from
engine/PINNED.md plus engine/patches/.

WHY OUTSIDE: keeping ~30k upstream files out of this repo is what makes
`git status` here mean something. See docs/ENGINE.md section 3.

THE RULE THIS SETS UP: all work happens on `forgemodding`; the upstream branch
stays pristine, so `git diff` against the pin is always exactly this project's
engine change. The workspace is deliberately NOT a declared read-only reference
(it is mutable by design), so that rule is what protects it.
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

UPSTREAM = "https://github.com/Card-Forge/forge"
BRANCH = "forgemodding"


def run(cmd, cwd=None, check=True):
    print("  $ %s" % " ".join(cmd))
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.stdout.strip():
        print("    " + r.stdout.strip().replace("\n", "\n    "))
    if r.returncode != 0:
        print("    ! " + (r.stderr or "").strip().replace("\n", "\n    "))
        if check:
            sys.exit(1)
    return r


def prereqs():
    print("Prerequisites")
    ok = True
    for tool, why in (("git", "cloning and patch management"),
                      ("mvn", "building"),
                      ("java", "building")):
        have = C.tool_available(tool)
        print("  %-6s %s   %s" % (tool, "OK     " if have else "MISSING", why))
        ok = ok and have
    print("\n  NOTE - open [I]: this machine's JDK has not been verified against Forge's")
    print("  target Java version. Check the upstream pom.xml before assuming a build")
    print("  failure is your fault, and record the answer in docs/ENGINE.md as [F].")
    print("\n  Android SDK + keystore are NOT needed here - that is milestone M4.")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", help="absolute path for the clone (outside this repo)")
    ap.add_argument("--check", action="store_true", help="prereqs only")
    ap.add_argument("--ref", default="master", help="upstream ref to pin (default: master)")
    args = ap.parse_args()

    ok = prereqs()
    if args.check:
        return 0 if ok else 1
    if not ok:
        print("\nBLOCKED: install the missing tools first, then re-run.")
        return 1
    if not args.workspace:
        print("\nPass --workspace with an absolute path OUTSIDE this repo, e.g.")
        print('  python tools/engine_bootstrap.py --workspace "E:\\Projekte\\forge-src"')
        return 2

    ws = os.path.normpath(args.workspace)
    if os.path.normcase(ws).startswith(os.path.normcase(C.REPO) + os.sep):
        print("\nREFUSED: the workspace must live outside this repo (see docs/ENGINE.md).")
        return 2

    if not os.path.isdir(os.path.join(ws, ".git")):
        print("\nCloning %s -> %s (large; this takes a while)" % (UPSTREAM, ws))
        run(["git", "clone", UPSTREAM, ws])
    else:
        print("\nWorkspace already a git repo; fetching.")
        run(["git", "-C", ws, "fetch", "origin"])

    pin = run(["git", "-C", ws, "rev-parse", args.ref]).stdout.strip()
    run(["git", "-C", ws, "checkout", "-B", BRANCH, pin])

    os.makedirs(os.path.join(C.REPO, "engine"), exist_ok=True)
    with open(os.path.join(C.REPO, "engine", "workspace.local.json"), "w", encoding="utf-8") as f:
        json.dump({"workspace": ws, "upstream": UPSTREAM, "branch": BRANCH}, f, indent=2)

    print("\nPinned %s at %s" % (args.ref, pin))
    print("Workspace bound in engine/workspace.local.json (gitignored).")
    print("\nNOW UPDATE engine/PINNED.md by hand with:")
    print("  commit:    %s" % pin)
    print("  build.txt: %s" % (C.install_build_txt() or "(install unbound)"))
    print("  pinned on: today")
    print("\nThen: python tools/engine_build.py  - build ONCE UNMODIFIED before writing")
    print("any patch, so a later failure is attributable to your change and not the setup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
