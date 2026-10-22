#!/usr/bin/env python3
"""Complete recovery init's first-party files from the same pinned build tree.

This does not download donor binaries, touch the device tree, or create an image.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import struct
import sys
import tempfile
from pathlib import Path

BOOT_FILES = {
    "system/bin/logd": ("built", "system/bin/logd"),
    "system/lib64/libcap.so": ("built", "system/lib64/libcap.so"),
    "init.recovery.mksh.rc": ("source", "bootable/recovery/etc/init.recovery.mksh.rc"),
}
INIT_IMPORTS = ("import /init.recovery.logd.rc",
                "import /init.recovery.mksh.rc")
ROOT_PREFIX = Path("out/target/product/songyuan/recovery/root")


def check_elf_arm64(path: Path) -> None:
    header = path.read_bytes()[:20]
    if len(header) < 20 or header[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", header, 18)[0] != 183:
        raise ValueError("not a same-build ARM64 ELF: " + str(path))


def finalize(twrp: Path) -> list[str]:
    twrp = twrp.resolve(strict=True)
    product = twrp / "out/target/product/songyuan"
    root = twrp / ROOT_PREFIX
    init = root / "system/etc/init/hw/init.rc"
    logd_init = root / "init.recovery.logd.rc"
    if not init.is_file() or not logd_init.is_file():
        raise ValueError("TWRP recovery init rc or logd service rc is absent")
    script = init.read_text(errors="replace")
    if any(item not in script for item in INIT_IMPORTS):
        raise ValueError("pinned TWRP init imports changed")
    if "service logd /system/bin/logd" not in logd_init.read_text(errors="replace"):
        raise ValueError("logd recovery service contract changed")
    candidates: list[tuple[Path, Path, str]] = []
    for rel, (kind, src_rel) in BOOT_FILES.items():
        source = twrp / src_rel if kind == "source" else product / src_rel
        target = root / rel
        if not source.is_file() or source.is_symlink():
            raise ValueError("missing original build/source file: " + str(source))
        if kind == "built":
            check_elf_arm64(source)
        else:
            if "export ENV /etc/mkshrc" not in source.read_text(errors="replace"):
                raise ValueError("pinned TWRP mksh rc contract changed")
        if target.is_symlink():
            raise ValueError("refuse to replace recovery symlink: " + rel)
        if target.exists():
            if not target.is_file() or source.read_bytes() != target.read_bytes():
                raise ValueError("installed native file differs from same-build source: " + rel)
        candidates.append((source, target, rel))

    copied = []
    for source, target, rel in candidates:
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(rel)
        if source.read_bytes() != target.read_bytes():
            raise ValueError("byte mismatch after native boot-file materialization: " + rel)

    # The ramdisk-file manifests are generated before this post-compile step.
    # Re-create both from the final root instead of leaving stale inventories.
    files = sorted(
        f for f in root.rglob("*")
        if f.is_file() and not f.is_symlink()
    )
    rels = [p.relative_to(root).as_posix() for p in files]
    manifest = root / "ramdisk-files.txt"
    checksums = root / "ramdisk-files.sha256sum"
    if not manifest.is_file() or not checksums.is_file():
        raise ValueError("original TWRP recovery ramdisk manifest absent")
    excluded_hash = {"ramdisk-files.sha256sum", "prop.default", "linkerconfig/ld.config.txt"}
    manifest.write_text("\n".join(rels) + "\n")
    hashes = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(root).as_posix()
        if rel in excluded_hash or "/lib/modules/" in "/" + rel:
            continue
        hashes.append(hashlib.sha256(p.read_bytes()).hexdigest() + "  ./" + rel)
    checksums.write_text("\n".join(hashes) + "\n")
    print("PASS: first-party TWRP init boot files complete; copies=" +
          (",".join(copied) if copied else "none"))
    return copied


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="songyuan-boot-root-") as td:
        twrp = Path(td)
        product = twrp / "out/target/product/songyuan"
        root = twrp / ROOT_PREFIX
        init = root / "system/etc/init/hw/init.rc"
        rc = root / "init.recovery.logd.rc"
        init.parent.mkdir(parents=True, exist_ok=True)
        init.write_text("\n".join(INIT_IMPORTS) + "\n")
        rc.write_text("service logd /system/bin/logd\n")
        mksh = twrp / "bootable/recovery/etc/init.recovery.mksh.rc"
        mksh.parent.mkdir(parents=True)
        mksh.write_text("on init\n    export ENV /etc/mkshrc\n")
        for _, (kind, rel) in BOOT_FILES.items():
            if kind != "built":
                continue
            f = product / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"\x7fELF\x02\x01" + b"\x00" * 12 + b"\xb7\x00" + b"test")
        (root / "ramdisk-files.txt").write_text("original\n")
        (root / "ramdisk-files.sha256sum").write_text("original\n")
        assert len(finalize(twrp)) == 3
        assert len(finalize(twrp)) == 0
        for path in BOOT_FILES:
            assert (root / path).is_file()
        assert "system/bin/logd" in (root / "ramdisk-files.txt").read_text()
        assert "./system/bin/logd" in (root / "ramdisk-files.sha256sum").read_text()
    print("PASS: materialization, checksum inventory, repeatability, source identity")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 2:
        try:
            finalize(Path(sys.argv[1]))
        except ValueError as e:
            sys.exit("BLOCKED: " + str(e))
    else:
        sys.exit("Usage: complete_recovery_boot_root.py TWRP_DIR | --self-test")
