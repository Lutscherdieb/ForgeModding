# -*- coding: utf-8 -*-
"""Deploy this repo's content into the Forge install (and optionally a device).

    python tools/deploy.py                 # all planes -> PC install, via junction
    python tools/deploy.py --plane "Name"  # just one
    python tools/deploy.py --custom        # also copy custom/ -> %APPDATA%\\Forge\\custom
    python tools/deploy.py --android       # also adb push planes to the device
    python tools/deploy.py --status        # report what is deployed, change nothing

WHY A JUNCTION AND NOT A COPY: mklink /J needs no admin rights, and Win32
traverses junctions transparently - Forge, the Adventure Editor and Tiled all
just see a folder. The install becomes a render target while this repo stays
the source of truth, and the Adventure Editor's install-side writes land
directly in this repo with no pull-back step.

IDEMPOTENT BY DESIGN: a Forge reinstall removes the junction, so this script is
expected to be re-run. It asserts the deployed path is a REPARSE POINT and not
a real directory - a real directory there means content was authored inside the
install, which the installer will eventually delete.

CAUTION: the junction gives the Adventure Editor write access to this repo.
Verify R1 (does the editor round-trip JSON losslessly?) before trusting it with
real content - see PROJECT.md's direction notes.
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

ANDROID_RES = "/sdcard/Android/obb/forge.app/Forge/res/adventure"


def is_junction(path):
    """True when path exists and is a reparse point rather than a real dir."""
    if not os.path.exists(path):
        return False
    if hasattr(os, "readlink"):
        try:
            os.readlink(path)
            return True
        except OSError:
            pass
    try:
        return bool(os.lstat(path).st_file_attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except (AttributeError, OSError):
        return False


def junction_target(path):
    try:
        return os.path.normpath(os.path.realpath(path))
    except OSError:
        return None


def deploy_plane(plane, install, dry=False):
    src = os.path.join(C.REPO, "planes", plane)
    dst = os.path.join(install, "res", "adventure", plane)
    want = os.path.normpath(src)

    if is_junction(dst):
        if junction_target(dst) == want:
            print("ok       %s -> already junctioned correctly" % plane)
            return True
        print("repair   %s -> junction points at %s" % (plane, junction_target(dst)))
        if not dry:
            os.rmdir(dst)
    elif os.path.exists(dst):
        print("REFUSED  %s -> a REAL directory exists at %s" % (plane, dst))
        print("         Content authored inside the install will be lost when Forge updates.")
        print("         Move it into planes/%s, then re-run this script." % plane)
        return False

    if dry:
        print("would    %s -> mklink /J" % plane)
        return True
    r = subprocess.run(["cmd", "/c", "mklink", "/J", dst, want],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("FAILED   %s -> %s" % (plane, (r.stderr or r.stdout).strip()))
        return False
    print("created  %s -> %s" % (plane, dst))
    return True


def deploy_custom(dry=False):
    """custom/ -> %APPDATA%\\Forge\\custom. A copy, not a junction: this tree is
    small, and Forge's four CardStorageReaders read it at startup only."""
    src = os.path.join(C.REPO, "custom")
    if not os.path.isdir(src) or not os.listdir(src):
        print("skip     custom/ is empty")
        return True
    appdata = os.environ.get("APPDATA")
    if not appdata:
        print("BLOCKED  custom/ -> APPDATA is not set")
        return False
    dst = os.path.join(appdata, "Forge", "custom")
    print("%s custom/ -> %s" % ("would  " if dry else "copying", dst))
    if not dry:
        shutil.copytree(src, dst, dirs_exist_ok=True)
    print("         reminder: a card script with no edition entry is silently skipped,")
    print("         and set ALLOW_CUSTOM_CARDS_IN_DECKS_CONFORMANCE=true for legality checks.")
    return True


def deploy_android(planes, dry=False):
    if not C.tool_available("adb"):
        print("BLOCKED  android -> adb not installed (MTP is the documented fallback)")
        return False
    ok = True
    for plane in planes:
        src = os.path.join(C.REPO, "planes", plane)
        print("%s %s -> %s/" % ("would push" if dry else "pushing   ", plane, ANDROID_RES))
        if dry:
            continue
        r = subprocess.run(["adb", "push", src, ANDROID_RES + "/"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("FAILED   %s -> %s" % (plane, (r.stderr or r.stdout).strip()))
            ok = False
    print("         device paths differ across Android versions and Forge's own docs")
    print("         disagree on casing - confirm with: adb shell ls %s" % ANDROID_RES)
    print("         checksum both sides rather than trusting the push (assessment R2).")
    return ok


def status(install):
    print("Deployment status")
    print("install: %s" % (install or "(unbound)"))
    for plane in C.planes():
        dst = os.path.join(install or "", "res", "adventure", plane)
        if is_junction(dst):
            same = junction_target(dst) == os.path.normpath(os.path.join(C.REPO, "planes", plane))
            print("  %-24s junction %s" % (plane, "-> this repo" if same else "-> ELSEWHERE"))
        elif os.path.exists(dst):
            print("  %-24s REAL DIRECTORY in the install (not deployed from here)" % plane)
        else:
            print("  %-24s not deployed" % plane)
    if not C.planes():
        print("  (no planes authored yet)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plane", action="append", help="deploy only this plane (repeatable)")
    ap.add_argument("--custom", action="store_true", help="also deploy custom/ to APPDATA")
    ap.add_argument("--android", action="store_true", help="also adb push planes to a device")
    ap.add_argument("--status", action="store_true", help="report only, change nothing")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    install = C.install_root()
    if not install:
        print("BLOCKED: forge-common is not bound in references.local.json, so the")
        print("install root cannot be derived. Run /base:repo-setup, or bind it by hand.")
        return 2
    if not os.path.isdir(install):
        print("BLOCKED: derived install root does not exist: %s" % install)
        return 2

    if args.status:
        status(install)
        return 0

    planes = args.plane or C.planes()
    if not planes:
        print("No planes to deploy yet. Author one under planes/<Name>/ first;")
        print("the assessment's section 10 describes a seven-file starter.")
    ok = all(deploy_plane(p, install, args.dry_run) for p in planes)
    if args.custom:
        ok = deploy_custom(args.dry_run) and ok
    if args.android:
        ok = deploy_android(planes, args.dry_run) and ok

    print("\nNext: launch %s and press F9 for the console (commands are case-sensitive)."
          % os.path.join(install, "forge-adventure.cmd"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
