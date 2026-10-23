#!/usr/bin/env python3
"""Fail-closed final Songyuan recovery-root audit and OEM repair. No Android build."""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

OEM_GROUPS = ("SONGYUAN_NATIVE_SERVICES", "SONGYUAN_NATIVE_LIBRARIES", "SONGYUAN_NATIVE_CONFIG")
AVB = re.compile(r"(?:^|[,\s])avb(?:=[^,\s]+)?(?:[,\s]|$)", re.I)
SERVICE = re.compile(r"^\s*service\s+\S+\s+(/\S+)")
IMPORT = re.compile(r"^\s*import\s+(/\S+)")

def group(mk, name):
    lines = mk.splitlines()
    matches = [i for i,s in enumerate(lines) if s.startswith(name + " :=")]
    if len(matches) != 1:
        raise RuntimeError("Expected exactly one make variable: " + name)
    i = matches[0]
    line = lines[i].split(":=",1)[1].strip()
    result = []
    while True:
        continuation = line.endswith("\\")
        result.extend(line.rstrip("\\").strip().split())
        if not continuation: break
        i += 1
        if i >= len(lines): raise RuntimeError("Unterminated: "+name)
        line = lines[i].strip()
    if len(result) != len(set(result)): raise RuntimeError("Duplicate: "+name)
    return result

def hash_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20), b""): h.update(chunk)
    return h.hexdigest()

def safe(root, rel):
    if rel.startswith("/") or "\x00" in rel or ".." in Path(rel).parts or not rel:
        raise RuntimeError("Unsafe path "+repr(rel))
    p = root / rel
    if not p.parent.resolve().is_relative_to(root.resolve()):
        raise RuntimeError("Symlink directory escapes root: "+rel)
    return p

def require(root, rel):
    p=safe(root,rel)
    if not p.is_file(): raise RuntimeError("Missing installed file: "+rel)
    return p

def check(dt, root, repair):
    mk=(dt/"device.mk").read_text()
    board=(dt/"BoardConfig.mk").read_text()
    manifest=json.loads((dt/"prebuilt/curated-manifest.json").read_text())
    if manifest["device"]!="songyuan" or manifest["source_firmware"]!="OS3.0.305.0.WGNIDXM":
        raise RuntimeError("Incorrect original ID305 source")
    if "BOARD_AVB_ENABLE := true" not in board or "TW_INCLUDE_WIFI := false" not in board:
        raise RuntimeError("Ekin-compatible image AVB config / no-Wi-Fi contract violated")
    oem=[x for k in OEM_GROUPS for x in group(mk,k)]
    if len(oem)!=59 or len(set(oem))!=len(oem):
        raise RuntimeError("Expected 59 unique selected ID305 OEM files")
    restored=[]
    for rel in oem:
        expected=manifest["files"].get(rel)
        if not expected: raise RuntimeError("OEM missing from audited manifest: "+rel)
        original=require(dt/"prebuilt",rel)
        if original.stat().st_size!=expected["bytes"] or hash_file(original)!=expected["sha256"]:
            raise RuntimeError("OEM source modified: "+rel)
        dest=safe(root,rel)
        if repair and not dest.exists() and not dest.is_symlink():
            dest.parent.mkdir(parents=True,exist_ok=True)
            safe(root,rel)
            shutil.copy2(original,dest)
            restored.append(rel)
        if not dest.is_file() or dest.stat().st_size!=expected["bytes"] or hash_file(dest)!=expected["sha256"]:
            raise RuntimeError("OEM missing or invalid from final recovery root: "+rel)

    # Upstream TWRP owns init.recovery.mksh.rc, so device.mk MUST NOT
    # install the same destination a second time. The upstream root from
    # this exact compile omitted it: restore only from pinned Songyuan
    # upstream-equivalent source if it is still missing after staging.
    # No second Make/Soong owner for this upstream TWRP init import.
    # Restore only its canonical generic init contents as a packaging fallback.
    mksh_data=b"on init\n    export ENV /etc/mkshrc\n"
    mksh_dest=safe(root,"init.recovery.mksh.rc")
    if repair and not mksh_dest.exists() and not mksh_dest.is_symlink():
        mksh_dest.write_bytes(mksh_data)
        restored.append("init.recovery.mksh.rc")
    if not mksh_dest.is_file() or mksh_dest.read_bytes()!=mksh_data:
        raise RuntimeError("mksh init missing or modified in final recovery root")

    natives=group(mk,"SONGYUAN_RECOVERY_FILE_PATHS")
    for rel in natives: require(root,rel)
    modules=group(mk,"SONGYUAN_MODULE_CLOSURE")
    if len(modules)!=28:raise RuntimeError("Module list changed: "+str(len(modules)))
    for name in modules:require(root,"vendor/lib/modules/1.1/"+name)
    for name in ("vendor/lib/modules/1.1/modules.dep","system/bin/recovery","system/bin/init","sepolicy"):
        require(root,name)

    fstab=require(root,"system/etc/recovery.fstab").read_bytes()
    if fstab!=require(dt,"recovery.fstab").read_bytes():
        raise RuntimeError("Installed fstab differs from original Songyuan DT")
    if b"/mnt/vendor/mi_ext" not in fstab or b"wrappedkey" not in fstab:
        raise RuntimeError("Stock ID305 mi_ext / FBE flags lost")
    for p in root.rglob("*fstab*"):
        if p.is_file() and AVB.search(p.read_text(errors="replace")):
            raise RuntimeError("AVB flag still active: "+p.relative_to(root).as_posix())
    service_count=0
    for rc in root.rglob("*.rc"):
        if not rc.is_file():continue
        for line in rc.read_text(errors="replace").splitlines():
            m=SERVICE.match(line)
            if m:
                service_count+=1
                target=m.group(1).lstrip("/")
                if not (root/target).exists():
                    raise RuntimeError("Init service executable missing: "+rc.name+" => "+target)
    init=require(root,"system/etc/init/hw/init.rc").read_text()
    for line in init.splitlines():
        m=IMPORT.match(line)
        if m:
            name=m.group(1).lstrip("/").replace("$"+"{ro.hardware}","qcom")
            require(root,name)
    if "service recovery /system/bin/recovery" not in init:
        raise RuntimeError("TWRP recovery startup service missing")
    print("PASS: 59/59 hashed OEM; "+str(len(natives))+" native script/config files; 28/28 modules; "+
          str(service_count)+" service binaries; main init imports; stock-ID305 no-AVB fstab")
    print("Native ID305 OEM restored="+str(len(restored)))
    for rel in restored:print("RESTORED native ID305: "+rel)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("device_tree",type=Path)
    ap.add_argument("recovery_root",type=Path)
    ap.add_argument("--repair-missing-oem",action="store_true")
    args=ap.parse_args()
    check(args.device_tree.resolve(),args.recovery_root.resolve(),args.repair_missing_oem)
