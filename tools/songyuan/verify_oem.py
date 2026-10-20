#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path

if len(sys.argv) != 2:
    sys.exit("Usage: verify_oem.py /path/to/curated-ID305")
root = Path(sys.argv[1])
file = root / "curated-manifest.json"
if not file.is_file():
    sys.exit("FAIL: no original ID305 curated-manifest.json")
meta = json.loads(file.read_text())
if (meta.get("device") != "songyuan" or
    meta.get("source_firmware") != "OS3.0.305.0.WGNIDXM" or
    meta.get("kernel_included") is not True):
    sys.exit("FAIL: wrong device/firmware or missing stock kernel")
records = meta.get("files")
if not isinstance(records, dict) or meta.get("file_count") != len(records):
    sys.exit("FAIL: malformed OEM manifest")
actual = {p.relative_to(root).as_posix()
          for p in root.rglob("*") if p.is_file()}
if actual != set(records) | {"curated-manifest.json"}:
    sys.exit("FAIL: unexpected/missing OEM files; refusing unverified payload")
required = {
    "kernel",
    "vendor/bin/qseecomd",
    "vendor/bin/hlosminkdaemon",
    "vendor/bin/hw/android.hardware.security.onekeymint-service-qti",
    "vendor/bin/hw/android.hardware.gatekeeper-rust-service-qti",
    "vendor/bin/hw/android.hardware.secure_element-service.qti",
    "odm/bin/hw/android.hardware.weaver-service.thales",
    "odm/bin/hw/android.hardware.nfc-service-st",
    "odm/bin/hw/android.hardware.security.keymint-service.strongbox-thales",
    "odm/bin/hw/vendor.xiaomi.hardware.authsecretd",
    "vendor/lib64/vendor.xiaomi.hardware.oldcredential-V1-ndk.so",
    "odm/etc/vintf/manifest/vendor.xiaomi.hardware.miauthsecretd.xml",
    "vendor/etc/passwd",
    "vendor/etc/group",
    "odm/firmware/focaltech_ts_fw_songyuan.bin",
    "odm/etc/vintf/manifest/android.hardware.weaver-service.thales.xml",
    "odm/etc/vintf/manifest/nfc-service-st.xml",
    "vendor/etc/vintf/manifest/android.hardware.secure_element.xml",
    "vendor_dlkm/lib/modules/modules.load",
}
if required - set(records):
    sys.exit("FAIL: genuine ID305 missing native OEM assets: " +
             ", ".join(sorted(required - set(records))))
for rel, info in records.items():
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts:
        sys.exit("FAIL: unsafe OEM relative path")
    if p.parts[0] not in ("kernel", "vendor", "odm", "vendor_dlkm"):
        sys.exit("FAIL: non-ID305 OEM location")
    if "/etc/init/" in "/" + rel:
        sys.exit("FAIL: raw stock init RC must not enter recovery")
    f = root / p
    if not f.is_file() or f.is_symlink():
        sys.exit("FAIL: missing/symlinked OEM file " + rel)
    h = hashlib.sha256()
    with f.open("rb") as src:
        for part in iter(lambda: src.read(1024*1024), b""):
            h.update(part)
    if f.stat().st_size != info["bytes"] or h.hexdigest() != info["sha256"]:
        sys.exit("FAIL: OEM hash/length mismatch " + rel)
touch = records["odm/firmware/focaltech_ts_fw_songyuan.bin"]
if touch["bytes"] != 148352 or touch["sha256"] != "7a5e927deeda12ac9fe8ea0dbdd673702222ddccbc37088ffc84d7c328b85fcc":
    sys.exit("FAIL: not original ID305 focaltech v35 firmware")
with (root / "kernel").open("rb") as f:
    f.seek(0x38)
    if f.read(4) != b"ARM\x64":
        sys.exit("FAIL: not original uncompressed ARM64 kernel")
print(f"PASS: {len(records)} fully hashed ID305 assets, no /raw init RC")
print("SOURCE ONLY: no Android image, no service/decryption test performed")
