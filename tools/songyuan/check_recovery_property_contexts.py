#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

CONTEXT = re.compile(r"^(\S+)\s+u:object_r:([A-Za-z_][A-Za-z0-9_]*):s0(?:\s|$)")
TYPE_WORD = rb"(?<![A-Za-z0-9_]){}(?![A-Za-z0-9_])"


def audit(policy_bytes: bytes, context_texts: dict[str, str]) -> dict:
    if not policy_bytes:
        raise ValueError("compiled binary sepolicy absent or empty")
    if not context_texts:
        raise ValueError("compiled recovery root has no *property_contexts files")
    checked = {}
    missing = []
    for path, text in sorted(context_texts.items()):
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            m = CONTEXT.match(stripped)
            if not m or not m.group(1).startswith("twrp."):
                continue
            name, type_name = m.groups()
            present = bool(re.search(TYPE_WORD.replace(rb"{}", re.escape(type_name.encode())),
                                     policy_bytes))
            checked[name] = {"context_type": type_name, "policy_name_present": present,
                             "source": path}
            if not present:
                missing.append(name + " → " + type_name)
    if "twrp.modules.loaded" not in checked:
        missing.append("missing explicit twrp.modules.loaded compiled property context")
    return {"mode": "compiled sepolicy type-NAME presence for twrp.* property contexts only",
            "checks": checked, "errors": missing, "runtime_selinux_verified": False}


def self_test() -> None:
    context = {"plat_property_contexts":
               "twrp.modules.loaded u:object_r:songyuan_twrp_prop:s0 exact bool\n"}
    valid = audit(b"foo\x00songyuan_twrp_prop\x00bar", context)
    assert len(valid["checks"]) == 1 and valid["errors"] == []
    rejected = audit(b"foo\x00default_prop\x00bar", context)
    assert len(rejected["errors"]) == 1
    assert "missing explicit twrp.modules.loaded compiled property context" in audit(
        b"other\x00", {"f": "vendor.foo u:object_r:vendor_prop:s0\n"})["errors"]
    try:
        audit(b"foo", {})
    except ValueError:
        pass
    else:
        raise AssertionError("empty policy contexts allowed")
    print("PASS: exact Songyuan TWRP property type mismatch is fail-closed")


def run(root: Path, out: Path) -> None:
    p = root / "sepolicy"
    if not p.is_file():
        raise ValueError("native recovery sepolicy not installed")
    contexts = {}
    for path in sorted(root.rglob("*property_contexts")):
        if path.is_file() and not path.is_symlink():
            contexts[path.relative_to(root).as_posix()] = path.read_text(errors="replace")
    report = audit(p.read_bytes(), contexts)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "NATIVE-PROPERTY-POLICY-AUDIT.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if report["errors"]:
        raise ValueError("compiled policy omits types referenced by TWRP property contexts; "
                         "see PRIVATE audit JSON")
    print("PASS: TWRP property context type-name guard; "
          "SELinux runtime / allow rules NOT PROVEN")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("root", nargs="?", type=Path)
    ap.add_argument("out", nargs="?", type=Path)
    opts = ap.parse_args()
    try:
        if opts.self_test:
            if opts.root or opts.out:
                ap.error("--self-test takes no directories")
            self_test()
        else:
            if not opts.root or not opts.out:
                ap.error("requires COMPILED_RECOVERY_ROOT PRIVATE_OUTPUT_DIR")
            run(opts.root, opts.out)
    except (OSError, ValueError, AssertionError) as e:
        sys.exit("BLOCKED: " + str(e))
