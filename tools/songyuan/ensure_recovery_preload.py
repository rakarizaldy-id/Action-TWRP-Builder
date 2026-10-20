#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import re
import sys

PRELOAD = "/system/lib64/libsongyuan_memset_compat.so"
TARGET = re.compile(r"(?m)^service[ \t]+recovery[ \t]+/system/bin/recovery(?:[ \t]+[^\r\n]*)?$")
ANY_RECOVERY = re.compile(r"(?m)^service[ \t]+recovery[ \t]+[^\r\n]+$")
BOUNDARY = re.compile(r"(?m)^(?:service|on|import)[ \t]+")
PRELOAD_LINE = re.compile(r"(?m)^[ \t]+setenv[ \t]+LD_PRELOAD[ \t]+([^\r\n]+)$")


def patched_content(source: str) -> tuple[str, bool]:
    matches = list(TARGET.finditer(source))
    all_services = list(ANY_RECOVERY.finditer(source))
    if len(matches) != 1 or len(all_services) != 1:
        raise ValueError("expected exactly one canonical recovery /system/bin/recovery init service")
    match = matches[0]
    rest = source[match.end():]
    boundary = BOUNDARY.search(rest)
    block_end = match.end() + boundary.start() if boundary else len(source)
    stanza = source[match.end():block_end]
    existing = PRELOAD_LINE.findall(stanza)
    if existing:
        if len(existing) != 1 or existing[0].strip() != PRELOAD:
            raise ValueError("existing recovery service LD_PRELOAD differs or is duplicated")
        return source, False
    newline = "\r\n" if "\r\n" in source else "\n"
    if not rest.startswith(newline):
        raise ValueError("unexpected recovery service header formatting")
    return (source[:match.end()] + newline +
            "    setenv LD_PRELOAD " + PRELOAD + source[match.end():]), True


def self_test() -> None:
    fixture = """on init
    setprop sys.usb.configfs 1

service recovery /system/bin/recovery
    class main
    user root

service vendor.qseecomd /vendor/bin/qseecomd
    user root
"""
    changed, first = patched_content(fixture)
    assert first and changed.count("    setenv LD_PRELOAD " + PRELOAD) == 1
    assert changed.index("LD_PRELOAD") < changed.index("service vendor.qseecomd")
    same, second = patched_content(changed)
    assert not second and same == changed
    for bad in (
        fixture.replace("service recovery /system/bin/recovery",
                        "service recovery /other/binary"),
        fixture + "\nservice recovery /system/bin/recovery\n    user root\n",
        fixture.replace("    class main",
                        "    setenv LD_PRELOAD /system/lib64/unrelated.so\n    class main"),
    ):
        try:
            patched_content(bad)
        except ValueError:
            continue
        raise AssertionError("unsafe init contract accepted")
    print("PASS: preload insertion is single-service, idempotent, and fail-closed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("root", nargs="?", type=Path)
    args = parser.parse_args()
    if args.self_test:
        if args.root:
            parser.error("--self-test cannot take a built root")
        self_test()
        return
    if args.root is None:
        parser.error("compiled recovery/root is required")
    root = args.root.resolve()
    shim = root / PRELOAD.lstrip("/")
    init = root / "system/etc/init/hw/init.rc"
    if not shim.is_file() or not init.is_file():
        raise ValueError("source-built recovery shim or init service file is missing")
    source = init.read_text()
    altered, changed = patched_content(source)
    if changed:
        init.write_text(altered)
    assert patched_content(init.read_text())[1] is False
    print("PASS: recovery-only LD_PRELOAD with first-party shim installed; "
          "static source/ELF checks still required; not boot-proof")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, AssertionError) as e:
        sys.exit("FAIL CLOSED: " + str(e))
