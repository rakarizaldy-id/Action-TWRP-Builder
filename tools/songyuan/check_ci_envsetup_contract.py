#!/usr/bin/env python3
"""Fail closed if CI sources Android envsetup under bash nounset."""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    sys.exit("Usage: check_ci_envsetup_contract.py WORKFLOW")
lines = Path(sys.argv[1]).read_text().splitlines()
required = {
    "Audit complete Soong and Make graph without Android compilation": False,
    "Compile complete pre-image recovery tree": False,
}
current = None
section_start = None
for idx, line in enumerate(lines):
    if line.startswith("      - name: "):
        current = line.removeprefix("      - name: ")
        section_start = idx
    if current not in required or "source build/envsetup.sh" not in line:
        continue
    if section_start is None:
        sys.exit("BLOCKED: envsetup outside named CI step")
    preceding = lines[section_start:idx]
    # TWRP16 envsetup.sh may expand optional unset vars such as TOP.
    if "          set -eo pipefail" not in preceding:
        sys.exit("BLOCKED: CI envsetup needs set -eo pipefail: " + current)
    if any(s.strip() in {"set -u", "set -eu", "set -euo pipefail",
                         "set -uo pipefail", "set -eu -o pipefail"}
           for s in preceding):
        sys.exit("BLOCKED: nounset active during TWRP16 envsetup: " + current)
    if required[current]:
        sys.exit("BLOCKED: unexpected repeated envsetup: " + current)
    required[current] = True
if not all(required.values()):
    sys.exit("BLOCKED: expected audit and compile entrypoints are missing")
joined = "\n".join(lines)
if 'm --skip-ninja "$preimage"' not in joined:
    sys.exit("BLOCKED: graph-only preflight command missing")
if joined.count('if: $' + '{{ inputs.graph_only == false }}') != 3:
    sys.exit("BLOCKED: unsafe graph-only CI guard")
print("PASS: graph and compile envsetup shell modes, graph-only separation")
