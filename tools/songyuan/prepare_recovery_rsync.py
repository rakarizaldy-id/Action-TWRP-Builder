#!/usr/bin/env python3
"""Preserve populated recovery directories when baseline ramdisk uses symlinks."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SAFE_PARTITIONS = frozenset({
    "system", "vendor", "odm", "product", "system_ext",
    "system_dlkm", "vendor_dlkm", "odm_dlkm", "mi_ext",
})
SAFE_REL = re.compile(r"[A-Za-z0-9_.@+-]+(?:/[A-Za-z0-9_.@+-]+)*\Z")


def exclude_conflicting_symlinks(source: Path, recovery: Path, output: Path) -> list[str]:
    if source.name != "root" or recovery.name != "root" or source == recovery:
        raise ValueError("expected distinct baseline/root and recovery/root directories")
    if not source.is_dir() or not recovery.is_dir():
        raise ValueError("baseline and recovery roots must already exist")
    excluded = []
    for item in sorted(source.rglob("*")):
        if not item.is_symlink():
            continue
        rel = item.relative_to(source)
        other = recovery / rel
        # Only links replacing populated physical recovery directories collide.
        if not other.is_dir() or other.is_symlink() or not any(other.iterdir()):
            continue
        rel_name = rel.as_posix()
        if rel.parts[0] not in SAFE_PARTITIONS or not SAFE_REL.fullmatch(rel_name):
            raise ValueError("unexpected symlink/directory conflict: " + rel_name)
        # The rsync source is the directory named "root", not its contents.
        # Thus paths in rsync's transfer list start with "root/".
        excluded.append("/root/" + rel_name)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(path + "\n" for path in excluded))
    for path in excluded:
        print("PRESERVE: populated native recovery directory " + path)
    print("PASS: baseline symlink collisions audited; " +
          str(len(excluded)) + " native recovery directories retained")
    return excluded


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="songyuan-rsync-") as temp:
        base = Path(temp)
        src = base / "baseline" / "root"
        dst = base / "recovery" / "root"
        (src / "odm").mkdir(parents=True)
        (src / "odm" / "firmware").symlink_to("/vendor/firmware")
        (src / "vendor").symlink_to("/system/vendor")
        (src / "default.prop").write_text("ro.test=1\n")
        (dst / "odm" / "firmware").mkdir(parents=True)
        (dst / "odm" / "firmware" / "native.fw").write_bytes(b"songyuan-original")
        (dst / "vendor" / "lib64").mkdir(parents=True)
        (dst / "vendor" / "lib64" / "native.so").write_bytes(b"songyuan-original")
        filters = base / "filters.txt"
        paths = exclude_conflicting_symlinks(src, dst, filters)
        assert paths == ["/root/odm/firmware", "/root/vendor"], paths
        assert filters.read_text() == "/root/odm/firmware\n/root/vendor\n"
        if shutil.which("rsync"):
            subprocess.run(
                ["rsync", "-a", "--exclude-from=" + str(filters),
                 str(src), str(base / "recovery")], check=True,
                capture_output=True, text=True
            )
            assert (dst / "odm" / "firmware" / "native.fw").read_bytes() == b"songyuan-original"
            assert (dst / "vendor" / "lib64" / "native.so").read_bytes() == b"songyuan-original"
            assert (dst / "default.prop").read_text() == "ro.test=1\n"
        print("PASS: both nested and top-level symlink collisions preserve native files")


def main() -> None:
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        return
    if len(sys.argv) != 4:
        raise SystemExit("Usage: prepare_recovery_rsync.py BASE_ROOT RECOVERY_ROOT EXCLUDES")
    try:
        exclude_conflicting_symlinks(
            Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
        )
    except ValueError as exc:
        raise SystemExit("BLOCKED: " + str(exc))


if __name__ == "__main__":
    main()
