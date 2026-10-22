#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

if len(sys.argv) != 3:
    sys.exit("usage: export_native_boot_contract.py ELF_BUNDLE_DIR BUILT_RECOVERY_ROOT")
out, root = (Path(p).resolve() for p in sys.argv[1:])
if not out.is_dir() or not root.is_dir():
    sys.exit("built root or private export root missing")

critical = (
    "system/bin/recovery",
    "system/bin/servicemanager",
    "system/bin/hwservicemanager",
    "system/bin/vndservicemanager",
    "system/bin/keystore2",
    "system/bin/twrp",
    "system/bin/logd",
    "system/lib64/libcap.so",
    "system/lib64/libsongyuan_memset_compat.so",
    "init.recovery.ldconfig.rc",
    "init.recovery.logd.rc",
    "init.recovery.mksh.rc",
    "init.recovery.usb.rc",
    "system/etc/init/hw/init.rc",
    "system/etc/init/hwservicemanager.rc",
    "system/etc/init/vndservicemanager.rc",
    "system/etc/init/keystore2.rc",
    "sepolicy",
)
elfs = (
    "system/bin/recovery",
    "system/bin/servicemanager",
    "system/bin/hwservicemanager",
    "system/bin/vndservicemanager",
    "system/bin/keystore2",
    "system/bin/twrp",
    "system/bin/logd",
    "system/lib64/libcap.so",
    "system/lib64/libsongyuan_memset_compat.so",
)
scopes = (
    "system/bin",
    "system/lib64/libcap.so",
    "system/lib64/libsongyuan_memset_compat.so",
    "system/etc/init",
    "system/etc/selinux",
    "plat_property_contexts",
    "vendor_property_contexts",
    "odm_property_contexts",
    "product_property_contexts",
    "system_ext_property_contexts",
    "init.recovery.ldconfig.rc",
    "init.recovery.logd.rc",
    "init.recovery.mksh.rc",
    "init.recovery.usb.rc",
    "init.recovery.qcom.rc",
    "system/etc/recovery.fstab",
    "sepolicy",
    "file_contexts",
    "file_contexts.bin",
    "plat_keystore2_key_contexts",
    "product/etc/selinux/product_keystore2_key_contexts",
)
missing = [rel for rel in critical if not (root / rel).is_file()]
nonarm = []
for rel in elfs:
    p = root / rel
    if not p.is_file():
        continue
    with p.open("rb") as f:
        header = f.read(20)
    if (len(header) < 20 or header[:6] != b"\x7fELF\x02\x01"
            or struct.unpack_from("<H", header, 18)[0] != 183):
        nonarm.append(rel)
stock_policy_sha = "d4758dfc17514b605b40992ab00bf37e75a90cabbfe37dda5829e082a4abdc38"
policy_file = root / "sepolicy"
if policy_file.is_file() and hashlib.sha256(policy_file.read_bytes()).hexdigest() == stock_policy_sha:
    missing.append("native recovery sepolicy absent: still identical to original stock ID305")


shim = root / "system/lib64/libsongyuan_memset_compat.so"
if shim.is_file():
    import subprocess
    inspected = subprocess.run(["readelf", "-Ws", str(shim)],
                               capture_output=True, text=True, check=False)
    definitions = set()
    if inspected.returncode == 0:
        for line in inspected.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 8 and parts[6] != "UND":
                definitions.add(parts[-1].split("@", 1)[0])
    for symbol in ("android_memset16", "android_memset32"):
        if symbol not in definitions:
            missing.append("source-built shim does not export " + symbol)

capfile = root / "system/lib64/libcap.so"
if capfile.is_file():
    import subprocess
    run = subprocess.run(["readelf", "-Ws", str(capfile)], text=True,
                         capture_output=True, check=False)
    exports = set()
    if run.returncode == 0:
        for line in run.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 8 and parts[6] != "UND":
                exports.add(parts[-1].split("@", 1)[0])
    for symbol in ("cap_init", "cap_clear", "cap_set_flag", "cap_set_proc", "cap_free"):
        if symbol not in exports:
            missing.append("libcap.so unresolved strong symbol: " + symbol)

init_path = root / "system/etc/init/hw/init.rc"
if init_path.is_file():
    init = init_path.read_text(errors="replace")
    if "service recovery /system/bin/recovery" not in init:
        missing.append("init.rc: service recovery")
    if "init.recovery.ldconfig.rc" not in init:
        missing.append("init.rc: TWRP recovery linker import")
    if "init.recovery.usb.rc" not in init:
        missing.append("init.rc: TWRP recovery USB import")

report = {
    "device": "songyuan",
    "firmware": "OS3.0.305.0.WGNIDXM",
    "mode": "built recovery-root files only; no recovery.img",
    "required": list(critical),
    "missing": sorted(set(missing)),
    "not_arm64": sorted(nonarm),
    "source_root_verified_complete": False,
    "eligible_for_user_flash": False,
    "v16_used_as_binary_input": False,
    "live_boot_success": False,
    "files": {},
}
report_file = out / "NATIVE-BOOT-CONTRACT.json"
def save():
    report_file.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
save()
if missing or nonarm:
    print("BLOCKED: incomplete first-party recovery boot root")
    for item in sorted(set(missing)):
        print("  MISSING_BOOT_CONTRACT: " + item)
    for item in sorted(set(nonarm)):
        print("  NON_ARM64_BOOT_CONTRACT: " + item)
    sys.exit(18)

dest = out / "native-boot-contract"
total_bytes = 0
for rel in scopes:
    start = root / rel
    if not start.exists():
        continue
    for src in sorted(start.rglob("*")) if start.is_dir() else (start,):
        if src.is_dir():
            continue
        subpath = src.relative_to(root)
        if subpath.suffix.lower() in (".img", ".pk8", ".pem", ".key", ".der"):
            raise RuntimeError("unexpected prohibited artifact in boot contract")
        target = dest / subpath
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            link = src.readlink().as_posix()
            if (not link or "\\x00" in link or ".." in Path(link).parts
                    or (link.startswith("/") and not link.startswith("/system/"))):
                raise RuntimeError("unsafe Android recovery symlink in built root")
            target.symlink_to(link)
            report["files"][subpath.as_posix()] = {"symlink_target": link}
            continue
        if not src.is_file():
            raise RuntimeError("unexpected non-file build-root entry")
        size = src.stat().st_size
        total_bytes += size
        if total_bytes > 450 * 1024 * 1024:
            raise RuntimeError("boot contract output unexpectedly large")
        shutil.copy2(src, target)
        report["files"][subpath.as_posix()] = {
            "bytes": size,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
report["source_root_verified_complete"] = True
report["files_count"] = len(report["files"])
report["files_bytes"] = total_bytes
save()
print(f"PASS: complete first-party TWRP boot-root inventory ({len(report['files'])} files) for PRIVATE offline audit; no IMG")
