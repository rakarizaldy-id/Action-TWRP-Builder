#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from pathlib import Path

if len(sys.argv) != 3:
    sys.exit("Usage: audit_compiled_runtime.py ARTIFACT_DIR COMPILED_RECOVERY_ROOT")

dst = Path(sys.argv[1])
root = Path(sys.argv[2])
require = [
    "system/bin/servicemanager",
    "system/lib64/libbinder.so",
    "system/lib64/libbinder_ndk.so",
]
files = ["recovery"] + ["paired-runtime/" + s for s in require]
results = {"device": "songyuan", "firmware": "OS3.0.305.0.WGNIDXM",
           "artifact_type": "compiled_binary_only_NOT_FLASHABLE",
           "runtime_pair_ready": False, "eligible_for_test_image_assembly": False,
           "files": {}, "missing_runtime": [],
           "full_stock_elf_needed_closure_verified": False,
           "hard_blockers": []}

def readelf(path: Path, option: str):
    x = subprocess.run(["readelf", option, str(path)], text=True,
                       capture_output=True, check=False)
    if x.returncode:
        raise RuntimeError(f"readelf {option} failed: {path}: {x.stderr[:250]}")
    return x.stdout

for name in files:
    path = dst / name
    if not path.is_file():
        if name == "recovery":
            sys.exit("FAIL: no compiled ARM64 TWRP recovery executable")
        results["missing_runtime"].append(name)
        continue
    data = path.read_bytes()
    if data[:6] != b"\x7fELF\x02\x01":
        sys.exit(f"FAIL: not ELF64 little-endian: {name}")
    hdr = readelf(path, "-h")
    if "AArch64" not in hdr:
        sys.exit(f"FAIL: not ARM64: {name}")
    dynamic = readelf(path, "-d")
    notes = readelf(path, "-n")
    markers = []
    for label, code in (("RECO", 0x5245434f), ("VNDR", 0x564e4452),
                        ("SYST", 0x53595354)):
        if code.to_bytes(4, "little") in data:
            markers.append(label)
    item = {
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "elf_machine": "AArch64",
        "binder_parcel_header_candidates_NOT_PROOF": markers,
        "needed": [
            line.strip().split("[", 1)[-1].rstrip("]")
            for line in dynamic.splitlines() if "(NEEDED)" in line
        ],
        "build_id_lines": [
            line.strip() for line in notes.splitlines() if "Build ID:" in line
        ][:4],
    }
    results["files"][name] = item

if results["missing_runtime"]:
    results["hard_blockers"].append(
        "Compiled recovery-root servicemanager/libbinder/libbinder_ndk pair is incomplete; "
        "cannot replace any framework library from this artifact."
    )
else:
    results["runtime_pair_ready"] = True
    results["eligible_for_test_image_assembly"] = False

results["hard_blockers"].append(
    "Live ID305 Weaver/eSE1 Binder endpoint registration and getConfig not proven."
)
results["hard_blockers"].append(
    "KeyStorage refusal of upgraded KeyMint blob not verified on compiled source."
)
results["hard_blockers"].append(
    "ID305 QTI eSE TA readability/mount and ST NFC functionality not proven."
)

report = dst / "COMPILED-RUNTIME-ABI-AUDIT.json"
report.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
(dst / "NOT-READY-FOR-IMAGE-REPLACEMENT.txt").write_text(
    "STOP: offline compiled ELF is not proof of compatible Binder wire ABI.\n"
    + "\n".join(results["hard_blockers"]) + "\n"
)
if results["missing_runtime"]:
    print("BLOCKED: native recovery ELF exists but mandatory SAME-BUILD Binder runtime is incomplete: " +
          ", ".join(results["missing_runtime"]))
    print("WROTE PRIVATE FORENSIC AUDIT: " + str(report))
    sys.exit(7)
print("STATIC ELF PAIR INVENTORY COMPLETE (NOT LIVE BINDER COMPATIBILITY): " + str(report))
print("BUNDLED: Binder pair only. FULL recovery runtime closure and OEM stock image NOT verified.")
print("NO recovery.img produced. No flash operation. NO PIN test authorization.")
