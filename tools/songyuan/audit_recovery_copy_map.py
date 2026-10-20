#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
from check_id305_module_graph import make_words, selected

if len(sys.argv) != 2:
    sys.exit("usage: audit_recovery_copy_map.py CANONICAL_SONGYUAN_DT")

dt = Path(sys.argv[1]).resolve()
prebuilt = dt / "prebuilt"
raw = (prebuilt / "curated-manifest.json").read_bytes()
if hashlib.sha256(raw).hexdigest() != "d1eeb419dbcc7593a1b5d72fc5d66f783341b6b5dcdd11f42d27e3a852bc1fc2":
    sys.exit("BLOCKED: original OEM provenance manifest changed")
manifest = json.loads(raw)
entries = manifest["files"]
if len(entries) != 162 or manifest["source_firmware"] != "OS3.0.305.0.WGNIDXM":
    sys.exit("BLOCKED: unexpected OEM archive")

source = (dt / "device.mk").read_text()
board = dt / "BoardConfig.mk"
if "find-copy-subdir-files" in source:
    sys.exit("BLOCKED: implicit bulk copy of OEM files reintroduced")
names = ("SONGYUAN_NATIVE_SERVICES", "SONGYUAN_NATIVE_LIBRARIES",
         "SONGYUAN_NATIVE_CONFIG")
groups = {name: make_words(source, name) for name in names}
files = [path for group in groups.values() for path in group]
if len(files) != len(set(files)):
    sys.exit("BLOCKED: duplicate OEM install")
if not set(files) <= set(entries):
    sys.exit("BLOCKED: selected native file missing from genuine archive")

supplement_file = dt / "SONGYUAN_SUPPLEMENTAL_OEM_SHA256.json"
supplement_files = {}
extra_services = set()
if supplement_file.is_file():
    supplemental = json.loads(supplement_file.read_text())
    if supplemental.get("device") != "songyuan" or supplemental.get("source_firmware") != "OS3.0.305.0.WGNIDXM":
        sys.exit("BLOCKED: wrong supplemental native OEM provenance")
    supplement_files = supplemental.get("files", {})
    if not isinstance(supplement_files, dict) or len(supplement_files) != 29:
        sys.exit("BLOCKED: expected exactly 29 native supplemental OEM entries")
    extra_services = {"odm/bin/hw/vendor.xiaomi.hardware.vibratorfeature.service"}
    for name, info in supplement_files.items():
        if (name.startswith("/") or ".." in Path(name).parts
                or not name.startswith(("vendor/", "odm/"))
                or not isinstance(info, dict)):
            sys.exit("BLOCKED: invalid supplemental OEM path")
        item = dt / "recovery/root" / name
        if not item.is_file() or item.is_symlink() or item.stat().st_size != info.get("bytes"):
            sys.exit("BLOCKED: supplemental OEM file missing/size mismatch " + name)
        if hashlib.sha256(item.read_bytes()).hexdigest() != info.get("sha256"):
            sys.exit("BLOCKED: supplemental OEM hash mismatch " + name)

services = set(groups["SONGYUAN_NATIVE_SERVICES"])
rc_services = set()
root = dt / "recovery/root"
for rc in root.rglob("*.rc"):
    for line in rc.read_text().splitlines():
        tokens = line.split()
        if len(tokens) >= 3 and tokens[0] == "service":
            path = tokens[2].lstrip("/")
            if path.startswith(("vendor/bin/", "odm/bin/")):
                rc_services.add(path)
if services | extra_services != rc_services:
    sys.exit("BLOCKED: native executable allowlist differs from recovery init services")

# Original DT_NEEDED inventory; no one may assert this proves dlopen, ABI or runtime.
index = {path.rsplit("/", 1)[-1]: path for path in entries if path.endswith(".so")}
visited = set(services)
stack = list(services)
missing_from_oem = set()
while stack:
    for name in manifest["elf_dependencies"].get(stack.pop(), []):
        path = index.get(name)
        if path:
            if path not in visited:
                visited.add(path)
                stack.append(path)
        else:
            missing_from_oem.add(name)
native_libs = {p for p in visited if p.endswith(".so")}
if native_libs != set(groups["SONGYUAN_NATIVE_LIBRARIES"]):
    sys.exit("BLOCKED: native ELF dependency closure incomplete or overcopied")
sys_required = {"libapexsupport.so", "libbinder_ndk.so", "libc.so",
                "libdl.so", "liblog.so", "libm.so", "libvndksupport.so"}
if missing_from_oem != sys_required:
    sys.exit("BLOCKED: unknown external runtime SONAME assumptions")

seeds, modules = selected(board, prebuilt)
if len(modules) != len(set(modules)):
    sys.exit("BLOCKED: duplicate native module")
copied_mod = make_words(source, "SONGYUAN_MODULE_CLOSURE")
if set(copied_mod) != set(modules):
    sys.exit("BLOCKED: native module copy list differs from selected graph")
if "recovery/root/vendor/lib/modules/1.1/$(module)" not in source:
    sys.exit("BLOCKED: selected module destination differs from TWRP loader priority")
if "recovery/root/vendor/lib/modules/1.1/modules.dep" not in source:
    sys.exit("BLOCKED: no original modules.dep with selected subset")

root_rel = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
selected_root = set(make_words(source, "SONGYUAN_RECOVERY_FILE_PATHS"))
if root_rel != selected_root:
    sys.exit("BLOCKED: TWRP source files are not explicitly allowlisted")
if not set(supplement_files) <= selected_root:
    sys.exit("BLOCKED: original Songyuan extra files not installed in recovery")
if not {"odm/firmware/focaltech_ts_fw_songyuan.bin",
        "vendor/etc/ssg/ta_config.json"} <= set(files):
    sys.exit("BLOCKED: native security or touch source omitted")
assert "TARGET_PREBUILT_KERNEL := $(DEVICE_PATH)/prebuilt/kernel" in board.read_text()
mapping = {}
def add(rel: str, source_name: str) -> None:
    if rel in mapping:
        raise ValueError("duplicate recovery copy destination " + rel)
    mapping[rel] = source_name
for path in sorted(selected_root):
    add("recovery/root/" + path, "recovery/root/" + path)
for path in ("system/etc/recovery.fstab", "system/etc/twrp.flags"):
    add("recovery/root/" + path, path)
for path in files:
    add("recovery/root/" + path, "prebuilt/" + path)
for name in modules:
    add("recovery/root/vendor/lib/modules/1.1/" + name,
        "prebuilt/vendor_dlkm/lib/modules/" + name)
add("recovery/root/vendor/lib/modules/1.1/modules.dep",
    "prebuilt/vendor_dlkm/lib/modules/modules.dep")
actual = {p.relative_to(prebuilt).as_posix()
          for p in prebuilt.rglob("*") if p.is_file()}
if actual != set(entries) | {"curated-manifest.json"}:
    sys.exit("BLOCKED: original OEM inventory changed")
for rel, info in entries.items():
    item = prebuilt / rel
    if not item.is_file() or item.is_symlink() or item.stat().st_size != info["bytes"]:
        sys.exit("BLOCKED: OEM file missing/size mismatch " + rel)
    if hashlib.sha256(item.read_bytes()).hexdigest() != info["sha256"]:
        sys.exit("BLOCKED: original OEM content changed " + rel)
print(f"PASS: {len(mapping)} distinct explicitly selected recovery destinations, "
      f"{len(files)} native service/library/config files, {len(seeds)} module seeds "
      f"and {len(modules)} closed modules; all 162 original files SHA-verified")
print("NOT VERIFIED: Soong, external SONAME providers, dlopen, security service runtime, device boot")
