#!/usr/bin/env python3
import collections
from pathlib import Path
import re
import subprocess
import sys

REQUIRED = ("android_memset16", "android_memset32")


def readelf(path, arg):
    proc = subprocess.run(["readelf", arg, str(path)], text=True,
                          capture_output=True, check=False)
    if proc.returncode:
        raise RuntimeError(f"readelf failed on {path}: {proc.stderr}")
    return proc.stdout


def needed(path):
    return re.findall(r"\(NEEDED\)\s+Shared library: \[(.+?)\]", readelf(path, "-d"))


def dynamic_symbols(path):
    result = {name: {"undefined": False, "defined": False} for name in REQUIRED}
    for line in readelf(path, "-Ws").splitlines():
        parts = line.split()
        if len(parts) < 8:
            continue
        symbol = parts[7].split("@", 1)[0]
        if symbol not in result:
            continue
        if parts[6] == "UND" and parts[4] != "WEAK":
            result[symbol]["undefined"] = True
        if parts[6] != "UND" and parts[4] in ("GLOBAL", "WEAK"):
            result[symbol]["defined"] = True
    return result


def main(root):
    init = root / "system/etc/init/hw/init.rc"
    binary = root / "system/bin/recovery"
    minui = root / "system/lib64/libtwrpminui.so"
    for path in (init, binary, minui):
        if not path.is_file():
            raise RuntimeError(f"missing required image file: {path}")
    text = init.read_text(errors="replace")
    match = re.search(r"(?ms)^service\s+recovery\s+/system/bin/recovery[^\n]*\n(.*?)(?=^(?:service|on)\s|\Z)", text)
    if not match:
        raise RuntimeError("service recovery definition not found")
    lines = re.findall(r"^\s*setenv\s+LD_PRELOAD\s+(\S+)", match.group(1), re.M)
    preloads = [path.lstrip("/") for value in lines for path in value.split(":")]
    for name in preloads:
        if not (root / name).is_file():
            raise RuntimeError(f"LD_PRELOAD missing: {name}")
    q = collections.deque(["system/bin/recovery"])
    closure = set()
    while q:
        name = q.popleft()
        if name in closure:
            continue
        closure.add(name)
        for soname in needed(root / name):
            choices = [
                f"system/lib64/{soname}", f"vendor/lib64/{soname}",
                f"vendor/lib64/hw/{soname}", f"vendor/odm/lib64/{soname}"
            ]
            provider = next((p for p in choices if (root / p).is_file()), None)
            if provider is None:
                raise RuntimeError(f"missing DT_NEEDED in recovery closure: {name} -> {soname}")
            q.append(provider)
    needed_by_minui = dynamic_symbols(minui)
    unresolved = []
    for symbol in REQUIRED:
        if not needed_by_minui[symbol]["undefined"]:
            continue
        provided = [
            name for name in sorted(closure | set(preloads))
            if dynamic_symbols(root / name)[symbol]["defined"]
        ]
        print(f"{symbol}: provider={provided}")
        if not provided:
            unresolved.append(symbol)
    if unresolved:
        raise RuntimeError("unresolved recovery strong dynamic imports: "+", ".join(unresolved))
    print(f"PASS static preload/ELF closure; {len(closure)} libs; NOT boot-proof")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: check_minui_preload_closure.py EXTRACTED_RECOVERY_ROOT")
    try:
        main(Path(sys.argv[1]))
    except Exception as exc:
        sys.exit(f"FAIL: {exc}")
