#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

PIN = Path(__file__).with_name("id305_module_closure.json")

def pinned() -> dict:
    doc = json.loads(PIN.read_text())
    if doc["device"] != "songyuan" or doc["firmware"] != "OS3.0.305.0.WGNIDXM":
        raise ValueError("incorrect native firmware")
    names = doc["modules"]
    if len(names) != 73 or names != sorted(set(names)):
        raise ValueError("native archive's historical 73-module inventory drifted")
    return doc

def make_words(source: str, key: str) -> list[str]:
    lines = source.splitlines()
    matches = [i for i, line in enumerate(lines) if line.startswith(key + " :=")]
    if len(matches) != 1:
        raise ValueError("missing/ambiguous selective list " + key)
    i = matches[0]
    value = lines[i].split(":=", 1)[1].strip()
    while value.endswith("\\"):
        i += 1
        if i >= len(lines):
            raise ValueError("unterminated list " + key)
        value = value[:-1].strip() + " " + lines[i].strip()
    return value.split()

def native_dependencies(source: str) -> dict[str, list[str]]:
    result = {}
    for line in source.splitlines():
        if not line.strip():
            continue
        name, sep, dependencies = line.partition(":")
        if sep != ":" or name in result:
            raise ValueError("bad native modules.dep")
        result[name.strip()] = dependencies.split()
    return result

def selected(board: Path, curated: Path) -> tuple[list[str], list[str]]:
    text = board.read_text()
    m = re.findall(r'^TW_LOAD_VENDOR_MODULES\s*:=\s*"([^"]+)"', text, re.M)
    if len(m) != 1:
        raise ValueError("bad native loader seed list")
    seeds = m[0].split()
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("empty or duplicate loader seeds")
    if "TW_LOAD_PREBUILT_MODULES_AT_FIRST := true" not in text:
        raise ValueError("staged native modules are not prioritized")
    required = {"panel_event_notifier.ko", "xiaomi_touch.ko",
                "focaltech_touch_3685g_1.ko", "stm_st54se_gpio.ko", "dwc3-msm.ko"}
    if not required <= set(seeds):
        raise ValueError("missing touchscreen/secure element/USB native seed")
    table = native_dependencies((curated / "vendor_dlkm/lib/modules/modules.dep").read_text())
    seen = set()
    def visit(name: str) -> None:
        if name in seen:
            return
        if name not in table:
            raise ValueError("missing original module or dependency " + name)
        seen.add(name)
        for dep in table[name]:
            visit(dep)
    for seed in seeds:
        visit(seed)
    named = make_words((board.parent / "device.mk").read_text(), "SONGYUAN_MODULE_CLOSURE")
    if len(named) != len(set(named)) or set(named) != seen:
        raise ValueError("staged subset must equal exact OEM recursive dependency closure")
    if not seen <= set(pinned()["modules"]):
        raise ValueError("non-ID305 kernel module staged")
    return seeds, sorted(seen)

def assert_curated(root: Path, doc: dict) -> None:
    meta = json.loads((root / "curated-manifest.json").read_text())
    if meta["device"] != "songyuan" or meta["source_firmware"] != doc["firmware"]:
        raise ValueError("OEM identity")
    if set(meta["module_closure"]) != set(doc["modules"]):
        raise ValueError("OEM original archive changed")
    entries = meta["files"]
    needed = {"vendor_dlkm/lib/modules/" + x for x in doc["modules"]}
    needed |= {"vendor_dlkm/lib/modules/modules.dep", "vendor_dlkm/lib/modules/modules.load"}
    if not needed <= entries.keys():
        raise ValueError("incomplete original module archive")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--board", type=Path)
    ap.add_argument("--curated", type=Path)
    args = ap.parse_args()
    doc = pinned()
    if args.self_test:
        assert len(doc["modules"]) == 73
        print("PASS original native 73-module source inventory")
    if args.curated:
        assert_curated(args.curated, doc)
    if args.board:
        curated = args.curated or args.board.parent / "prebuilt"
        seeds, staged = selected(args.board, curated)
        print(f"PASS selective Songyuan loader: {len(seeds)} requested, "
              f"{len(staged)} dependency-closed genuine modules of 73 archived")

if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, AssertionError) as e:
        sys.exit("BLOCKED: " + str(e))
