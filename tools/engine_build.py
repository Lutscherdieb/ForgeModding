# -*- coding: utf-8 -*-
"""Build the workspace and install the resulting jar into the Forge install.

    python tools/engine_build.py               # build the mobile jar (Adventure)
    python tools/engine_build.py --no-install   # build only, leave the install alone

WHICH JAR MATTERS: forge-adventure.cmd launches the MOBILE jar, not the desktop
one - Adventure on PC is the Android UI running on desktop against the same
res/, from the same code. So an Adventure engine change is built and verified
against forge-gui-mobile-dev.

The installed jar is a build artifact, overwritten by any Forge update. That is
fine and expected: the patch series in this repo is the durable thing.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

MODULE = "forge-gui-mobile-dev"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-install", action="store_true")
    ap.add_argument("--module", default=MODULE)
    args = ap.parse_args()

    ws = C.workspace()
    if not ws or not os.path.isdir(ws):
        print("BLOCKED: no engine workspace. Run tools/engine_bootstrap.py first.")
        return 2
    if not C.tool_available("mvn"):
        print("BLOCKED: mvn is not installed. The engine track cannot build.")
        return 2

    print("Building %s in %s" % (args.module, ws))
    r = subprocess.run(["mvn", "-pl", args.module, "-am", "-DskipTests", "package"],
                       cwd=ws, text=True)
    if r.returncode != 0:
        print("")
        print("Build failed. Before assuming your patch is at fault: this machine's JDK")
        print("has not been verified against Forge's target Java version - that is an")
        print("open [I] in docs/ENGINE.md. Check the upstream pom.xml first.")
        return 1

    jars = glob.glob(os.path.join(ws, args.module, "target", "*jar-with-dependencies.jar"))
    if not jars:
        print("Built, but no jar-with-dependencies found under %s/target." % args.module)
        return 1
    print("Built: %s" % jars[0])

    if args.no_install:
        return 0
    install = C.install_root()
    if not install:
        print("BLOCKED: install root unbound; skipping the install step.")
        return 2
    dst = os.path.join(install, os.path.basename(jars[0]))
    shutil.copy2(jars[0], dst)
    print("Installed -> %s" % dst)
    print("")
    print("Note: this jar is PC-only. Engine features do not reach Android until the")
    print("M4 APK pipeline exists (Android SDK + Maven + keystore). Content still does.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
