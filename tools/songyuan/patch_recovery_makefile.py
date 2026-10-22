#!/usr/bin/env python3
"""Patch only the baseline-recovery rsync invocation in pinned AOSP Makefile."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ORIGINAL = (
    "rsync -a --exclude=sdcard $(IGNORE_RECOVERY_SEPOLICY) "
    "$(IGNORE_CACHE_LINK) $(TARGET_ROOT_OUT) $(TARGET_RECOVERY_OUT)"
)
REPLACEMENT = (
    "python3 $(GITHUB_WORKSPACE)/tools/songyuan/prepare_recovery_rsync.py "
    "$(TARGET_ROOT_OUT) $(TARGET_RECOVERY_ROOT_OUT) "
    "$(TARGET_RECOVERY_OUT)/songyuan-rsync-excludes.txt"
    " && rsync -a --exclude=sdcard "
    "--exclude-from=$(TARGET_RECOVERY_OUT)/songyuan-rsync-excludes.txt "
    "$(IGNORE_RECOVERY_SEPOLICY) $(IGNORE_CACHE_LINK) "
    "$(TARGET_ROOT_OUT) $(TARGET_RECOVERY_OUT)"
)


def patch(source: str) -> str:
    if source.count(ORIGINAL) != 1:
        raise ValueError("expected exactly one pinned AOSP recovery baseline rsync")
    if "INTERNAL_RECOVERY_RAMDISK_FILES_TIMESTAMP" not in source:
        raise ValueError("recovery ramdisk graph missing in upstream Makefile")
    out = source.replace(ORIGINAL, REPLACEMENT, 1)
    if out.count(REPLACEMENT) != 1 or ORIGINAL in out:
        raise ValueError("AOSP recovery packaging patch was incomplete")
    return out


def self_test() -> None:
    src = (
        "INTERNAL_RECOVERY_RAMDISK_FILES_TIMESTAMP := target\n"
        "\t$(hide) " + ORIGINAL + "\n"
        "\t$(hide) touch $@\n"
    )
    out = patch(src)
    assert out.count("\t$(hide) python3") == 1
    assert out.count("&& rsync -a") == 1
    assert out.count("--exclude-from=") == 1
    assert "touch $@" in out
    for bad in ("", src.replace(ORIGINAL, ""), src + ORIGINAL):
        try:
            patch(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("unrecognized or duplicated Makefile accepted")
    print("PASS: one verified AOSP recovery rsync owner patched, unchanged packaging target")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 2:
        file = Path(sys.argv[1])
        if not file.is_file():
            raise SystemExit("BLOCKED: AOSP Makefile does not exist")
        try:
            content = patch(file.read_text())
        except ValueError as exc:
            raise SystemExit("BLOCKED: " + str(exc))
        file.write_text(content)
        print("PASS: recovery baseline rsync now protects populated Songyuan directories")
    else:
        raise SystemExit("Usage: patch_recovery_makefile.py MAKEFILE | --self-test")
