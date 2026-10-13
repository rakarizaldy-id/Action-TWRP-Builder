#!/usr/bin/env bash
# PUBLIC, SOURCE-ONLY GitHub runner probe for official TWRP 16.
# Never fetch Songyuan private repositories, OEM, userdata, boot assets, or secrets.
# Never build recovery binaries/images, repack images, or publish a release.
set -euo pipefail
: "${GITHUB_WORKSPACE:?}" "${RUNNER_TEMP:?}"
SRC="$GITHUB_WORKSPACE/twrp"
LOGS="$RUNNER_TEMP/songyuan-full-source-sync"
TOOLBIN="$RUNNER_TEMP/songyuan-repo-bin"
CLANG="prebuilts/clang/host/linux-x86"
MIN_FREE_KIB=26214400  # 25 GiB reserve.
MIN_START_FREE_KIB=99614720  # At least 95 GiB free to start.
mkdir -p "$SRC" "$LOGS" "$TOOLBIN"
echo "SOURCE-ONLY: no private Songyuan OEM, tree, compile, or recovery.img"
nproc
free -h
df -hT / "$GITHUB_WORKSPACE" "$RUNNER_TEMP" | tee "$LOGS/disk-before.txt"
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
available_kib="$(df -Pk "$SRC" | awk 'END {print $4}')"
if (( available_kib < MIN_START_FREE_KIB )); then
  echo "::error::Need 95 GiB free at start; available ${available_kib} KiB"
  exit 20
fi
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  git curl ca-certificates python3
curl -fsSL --retry 3 https://storage.googleapis.com/git-repo-downloads/repo \
  -o "$TOOLBIN/repo"
chmod 0755 "$TOOLBIN/repo"
export PATH="$TOOLBIN:$PATH"
repo --version > "$LOGS/repo-version.txt" 2>&1 || true
cd "$SRC"
if ! repo init -u https://github.com/TWRP-Test/platform_manifest_twrp_aosp \
  -b twrp-16.0 --depth=1 > "$LOGS/init.log" 2>&1; then
  echo "::error::Official TWRP16 manifest init failed"
  tail -n 70 "$LOGS/init.log" || true
  exit 21
fi
repo manifest -o "$LOGS/effective-manifest.xml"
python3 - "$LOGS/effective-manifest.xml" "$CLANG" "$LOGS/manifest-summary.txt" <<'PY'
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
paths = [p.get('path') or p.get('name') for p in
         ET.parse(sys.argv[1]).getroot().findall('project')]
if len(paths) != 392 or len(set(paths)) != 392 or sys.argv[2] not in paths:
    raise SystemExit(f"Unexpected manifest: {len(paths)} paths; {len(set(paths))} unique")
Path(sys.argv[3]).write_text(f"manifest_projects={len(paths)}\nclang_path={sys.argv[2]}\n")
print(f"Official TWRP16 manifest projects: {len(paths)}")
PY
if [[ -e "$SRC/device/xiaomi/songyuan" || -e "$GITHUB_WORKSPACE/.songyuan-oem" ]]; then
  echo "::error::Private Songyuan files unexpectedly present on public runner"
  exit 22
fi
printf 'timestamp\tstage\telapsed_seconds\tfree_kib\tused_kib\n' \
  > "$LOGS/resource-heartbeat.tsv"
run_guarded() {
  local label="$1" limit="$2"
  shift 2
  local started=$SECONDS checks=0 rc=0 disk_stop=0
  echo "Starting $label; timeout=${limit}s; free disk reserve=25GiB"
  setsid timeout --signal=TERM --kill-after=40s "${limit}s" "$@" \
    > "$LOGS/${label}.log" 2>&1 &
  local pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    sleep 15
    checks=$((checks + 1))
    local used_kib free_kib
    used_kib="$(df -Pk "$SRC" | awk 'END {print $3}')"
    free_kib="$(df -Pk "$SRC" | awk 'END {print $4}')"
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(date +%s)" "$label" "$((SECONDS-started))" "$free_kib" "$used_kib" \
      >> "$LOGS/resource-heartbeat.tsv"
    if (( checks % 4 == 0 )); then
      echo "[$label] elapsed=$((SECONDS-started))s free_kib=$free_kib used_kib=$used_kib"
      tail -n 3 "$LOGS/${label}.log" || true
    fi
    if (( free_kib < MIN_FREE_KIB )); then
      echo "::error::$label: free disk under 25 GiB; terminating checkout"
      kill -TERM -- "-$pid" 2>/dev/null || true
      disk_stop=1
      break
    fi
  done
  wait "$pid" || rc=$?
  if (( disk_stop )); then rc=99; fi
  printf 'stage=%s exit_code=%s elapsed_seconds=%s\n' \
    "$label" "$rc" "$((SECONDS-started))" >> "$LOGS/stage-results.txt"
  df -hT "$SRC" | tee "$LOGS/disk-after-${label}.txt"
  if (( rc != 0 )); then
    echo "::error::$label failed (code $rc). Last 90 source-only log lines:"
    tail -n 90 "$LOGS/${label}.log" || true
  fi
  return "$rc"
}
# Proven large Clang project first, on the same runner as the full sync.
# Non-partial shallow clone is intentionally identical to successful test.
if ! run_guarded "clang" 2400 \
  repo sync -v -c -j1 --no-clone-bundle --no-tags --fail-fast "$CLANG"; then
  exit 30
fi
echo "Clang SHA: $(git -C "$SRC/$CLANG" rev-parse --verify HEAD)" \
  | tee "$LOGS/clang-revision.txt"
# Remaining source + final Clang consistency pass. Never stage private OEM.
if ! run_guarded "full-sync" 18000 \
  repo sync -v -c -j1 --no-clone-bundle --no-tags --fail-fast; then
  exit 31
fi
repo manifest -r -o "$LOGS/resolved-source-manifest.xml"
python3 - "$SRC" "$LOGS/resolved-source-manifest.xml" "$LOGS/synced-revisions.tsv" <<'PY'
import subprocess
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
root = Path(sys.argv[1])
projects = ET.parse(sys.argv[2]).getroot().findall('project')
lines = []
missing = []
for p in projects:
    rel = p.get('path') or p.get('name')
    directory = root / rel
    if not directory.is_dir():
        missing.append(rel)
        continue
    proc = subprocess.run(['git', '-C', str(directory), 'rev-parse', '--verify', 'HEAD'],
                          capture_output=True, text=True)
    if proc.returncode:
        missing.append(rel)
    else:
        lines.append(f'{rel}\t{proc.stdout.strip()}')
Path(sys.argv[3]).write_text('\n'.join(sorted(lines)) + '\n')
print(f'Synced projects: {len(lines)} / {len(projects)}')
if len(projects) != 392 or len(lines) != 392 or missing:
    raise SystemExit(f'Incomplete source lock: {len(missing)} missing: {missing[:15]}')
PY
sha256sum "$LOGS/resolved-source-manifest.xml" "$LOGS/synced-revisions.tsv" \
  > "$LOGS/source-lock-SHA256SUMS.txt"
df -hT "$SRC" | tee "$LOGS/final-disk.txt"
du -sh "$SRC" "$SRC/.repo" "$SRC/$CLANG" 2>/dev/null \
  | tee "$LOGS/source-sizes.txt"
{
  echo '### Official TWRP16 source-only sync: PASS'
  echo '392/392 project worktrees checked; no OEM, device tree, or build.'
  cat "$LOGS/source-sizes.txt" "$LOGS/final-disk.txt"
} >> "$GITHUB_STEP_SUMMARY"
echo "SUCCESS: 392 official source projects; no TWRP binary or image built."
