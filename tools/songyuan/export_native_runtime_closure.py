#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, re, shutil, subprocess, sys
from collections import deque
from pathlib import Path, PurePosixPath

if len(sys.argv) != 3:
    sys.exit("usage: export_native_runtime_closure.py ARTIFACT_DIR BUILT_RECOVERY_ROOT")
out, root = map(lambda x: Path(x).resolve(), sys.argv[1:])
assert (out / "recovery").is_file() and root.is_dir()
lib_dest = out / "runtime-closure"
lib_dest.mkdir(parents=True, exist_ok=True)
search_dirs = (
    "system/lib64", "lib64", "system_ext/lib64", "product/lib64",
    "vendor/lib64", "odm/lib64",
)

def readelf(path: Path, mode: str) -> str:
    proc = subprocess.run(["readelf", mode, str(path)], capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(f"readelf {mode} fails: {path}: {proc.stderr[-250:]}")
    return proc.stdout

def needed(elf: Path) -> list[str]:
    if "AArch64" not in readelf(elf, "-h"):
        raise RuntimeError(f"Not AArch64 ELF: {elf}")
    return re.findall(r"\(NEEDED\).*?\[([^\]]+)\]", readelf(elf, "-d"))

product_root = root.parent.parent
if root != product_root / "recovery" / "root":
    raise RuntimeError("Unexpected recovery root: refuse runtime fallback")
def locate(name: str) -> tuple[str, Path] | None:
    if not name or name != PurePosixPath(name).name or "/" in name:
        raise RuntimeError(f"Untrusted DT_NEEDED soname: {name}")
    choices = [(root / d / name, f"{d}/{name}") for d in search_dirs]
    choices += [
        (product_root / "system/lib64" / name, f"system/lib64/{name}"),
        (product_root / "system_ext/lib64" / name, f"system/lib64/{name}"),
    ]
    for src, rel in choices:
        if not src.is_file() and not src.is_symlink():
            continue
        for _ in range(12):
            if not src.is_symlink():
                break
            dest = os.readlink(src)
            src = product_root / dest.lstrip("/") if dest.startswith("/") else src.parent / dest
        else:
            raise RuntimeError(f"Symlink loop: {rel}")
        if not src.is_file():
            raise RuntimeError(f"Unresolvable same-build runtime link: {rel}")
        resolved = src.resolve()
        if not resolved.is_relative_to(product_root):
            raise RuntimeError(f"Runtime link left same-build product output: {rel}")
        return rel, resolved
    return None

primary = [out / "recovery", out / "paired-runtime/system/bin/servicemanager"]
for src in primary:
    if not src.is_file():
        raise RuntimeError(f"Missing source-built executable: {src}")
root_bins = root / "system/bin"
if not root_bins.is_dir():
    raise RuntimeError("No built system/bin in first-party recovery root")
extra_programs = []
for candidate in sorted(root_bins.rglob("*")):
    if not candidate.is_file():
        continue
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise RuntimeError("Recovery-root executable resolves outside source build root")
    with resolved.open("rb") as fp:
        elf_magic = fp.read(20)
    if not elf_magic.startswith(b"\x7fELF"):
        continue
    if len(elf_magic) < 20 or elf_magic[18:20] != b"\xb7\x00":
        raise RuntimeError("Non-AArch64 ELF shipped in original recovery root")
    extra_programs.append(candidate)
if not extra_programs:
    raise RuntimeError("Compiled recovery system/bin has no AArch64 executables")
queue = deque(primary + extra_programs)
seen_elf: set[str] = set()
found: dict[str, dict] = {}
missing: dict[str, list[str]] = {}
while queue:
    elf = queue.popleft()
    key = str(elf)
    if key in seen_elf:
        continue
    seen_elf.add(key)
    for soname in needed(elf):
        resolved = locate(soname)
        if resolved is None:
            missing.setdefault(soname, []).append(
                str(elf.relative_to(out)) if elf.is_relative_to(out)
                else "native-recovery-root")
            continue
        rel, real = resolved
        if rel in found:
            continue
        saved = lib_dest / rel
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(real, saved)
        if not saved.is_file() or saved.stat().st_size < 1:
            raise RuntimeError(f"Exported runtime missing: {rel}")
        with saved.open("rb") as fp:
            digest = hashlib.file_digest(fp, "sha256").hexdigest()
        found[rel] = {
            "sha256": digest,
            "bytes": saved.stat().st_size,
            "source_rel": real.relative_to(product_root).as_posix(),
            "dt_needed_name": soname,
        }
        queue.append(real)


install_candidates = (
    "twres",
    "res",
    "etc/recovery.fstab",
    "system/etc/recovery.fstab",
    "system/etc/init/se_omapi.rc",
    "system/bin/se_omapi",
    "system/bin/songyuan-touch-init.sh",
    "init.recovery.qcom.rc",
)
extras = {}
for rel in install_candidates:
    original = root / rel
    if not original.exists() or original.is_symlink():
        continue
    destination = out / "native-install-candidates" / rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    if original.is_dir():
        shutil.copytree(original, destination, dirs_exist_ok=False, symlinks=True)
        extras[rel] = "directory (offline REVIEW required)"
    elif original.is_file():
        shutil.copy2(original, destination)
        extras[rel] = hashlib.sha256(destination.read_bytes()).hexdigest()

report = {
    "device": "songyuan",
    "firmware": "OS3.0.305.0.WGNIDXM",
    "mode": "source-built AArch64 dependency closure ONLY; no recovery IMG",
    "primary_executables": ["recovery", "paired-runtime/system/bin/servicemanager"],
    "libs_exported": found,
    "native_install_candidates_NOT_APPROVED": extras,
    "libs_count": len(found),
    "built_recovery_aarch64_executables_checked": len(extra_programs),
    "missing_sonames": missing,
    "closure_complete_in_build_root": not missing,
    "eligible_for_stock_image_assembly": False,
    "why_not_ready": "Offline OEM ID305 ramdisk and init/linker/SELinux review and user-only phone test required.",
}
(out / "NATIVE-RUNTIME-CLOSURE.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
print(f"NATIVE CLOSURE scanned ELF={len(seen_elf)} source-built executables={len(extra_programs)} libs={len(found)} missing={len(missing)}; no IMG")
if missing:
    print("MISSING native build-root SONAMEs: " + ", ".join(sorted(missing)))
    sys.exit(9)
print("PASS: complete source-built DT_NEEDED closure, still NOT image-ready")
