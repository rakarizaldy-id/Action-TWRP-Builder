#!/usr/bin/env bash
# Public GitHub runner source-only experiment. NEVER access Songyuan private OEM.
set -euo pipefail
: "${GITHUB_WORKSPACE:?}" "${RUNNER_TEMP:?}" "${GITHUB_PATH:?}"
TARGET="prebuilts/clang/host/linux-x86"
SRC="$GITHUB_WORKSPACE/twrp"
LOGS="$RUNNER_TEMP/songyuan-clang-probe"
mkdir -p "$LOGS" "$SRC" "$RUNNER_TEMP/bin"
echo "SOURCE-ONLY TWRP16 Clang probe: no private OEM, device tree, or build"
nproc
free -h
df -hT / "$GITHUB_WORKSPACE" "$RUNNER_TEMP"
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends git curl ca-certificates python3
curl -fsSL --retry 3 https://storage.googleapis.com/git-repo-downloads/repo -o "$RUNNER_TEMP/bin/repo"
chmod 0755 "$RUNNER_TEMP/bin/repo"
export PATH="$RUNNER_TEMP/bin:$PATH"
repo --version | tee "$LOGS/repo-version.txt"
cd "$SRC"
repo init -u https://github.com/TWRP-Test/platform_manifest_twrp_aosp -b twrp-16.0 \
  --depth=1 > "$LOGS/init.log" 2>&1 || {
  tail -n 100 "$LOGS/init.log"
  exit 1
}
repo manifest -o "$LOGS/effective-manifest.xml"
python3 - "$LOGS/effective-manifest.xml" "$TARGET" <<'PY'
import sys
import xml.etree.ElementTree as ET
paths = {p.get("path") or p.get("name") for p in ET.parse(sys.argv[1]).getroot().findall("project")}
print("Official TWRP16 manifest paths:", len(paths))
if len(paths) < 300 or sys.argv[2] not in paths:
    raise SystemExit("Unexpected manifest or Clang project missing")
PY
echo "Target: $TARGET"
echo "Experiment: full shallow Git objects (NO blob:none partial clone)"
REMOTE="https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86"
if ! timeout 90s git ls-remote --exit-code "$REMOTE" refs/tags/android-16.0.0_r1 > "$LOGS/remote-tag.txt" 2> "$LOGS/remote-tag-error.txt"; then
  echo "::error::Could not query official AOSP Clang tag; see uploaded remote-tag-error.txt"
  cat "$LOGS/remote-tag-error.txt" || true
  exit 21
fi
cat "$LOGS/remote-tag.txt"
df -hT "$SRC"
# Build #6 hit its 600-second timeout on this exact large prebuilt.
# Allow 2400 seconds, and stop if free disk falls below 25 GiB.
minimum_kib=26214400
started="$SECONDS"
setsid timeout --signal=TERM --kill-after=30s 2400s \
  env GIT_TRACE="$LOGS/git-trace.log" GIT_TRACE2_EVENT="$LOGS/git-trace2.jsonl" \
    GIT_TRACE_CURL="$LOGS/git-curl.log" GIT_TRACE_CURL_NO_DATA=1 GIT_TERMINAL_PROMPT=0 \
  repo sync -v -c -j1 --no-clone-bundle --no-tags --fail-fast "$TARGET" \
  > "$LOGS/clang-sync.log" 2>&1 &
pid=$!
stopped_for_disk=0
checks=0
while kill -0 "$pid" 2>/dev/null; do
  sleep 10
  checks=$((checks + 1))
  if (( checks % 6 == 0 )); then
    echo "Clang sync heartbeat: $((SECONDS-started)) seconds elapsed"
    df -hT "$SRC"
    du -sh "$SRC/.repo" 2>/dev/null || true
    tail -n 3 "$LOGS/clang-sync.log" || true
  fi
  free_kib="$(df -Pk "$SRC" | awk 'END{print $4}')"
  if (( free_kib < minimum_kib )); then
    echo "::error::Free disk below 25 GiB; terminate isolated Clang checkout"
    kill -TERM -- "-$pid" 2>/dev/null || true
    stopped_for_disk=1
    break
  fi
done
rc=0
wait "$pid" || rc=$?
if (( stopped_for_disk )); then rc=99; fi
{
  printf 'target=%s\nexit_code=%s\nelapsed_seconds=%s\n' "$TARGET" "$rc" "$((SECONDS-started))"
  df -hT "$SRC"
  du -sh "$SRC/$TARGET" "$SRC/.repo" 2>/dev/null || true
} | tee "$LOGS/final-status.txt"
if (( rc != 0 )); then
  tail -n 100 "$LOGS/clang-sync.log" || true
  echo "Last Git command trace (public endpoints only):"
  tail -n 50 "$LOGS/git-trace.log" 2>/dev/null || true
  echo "Last Git HTTP trace (headers only, no payload):"
  tail -n 40 "$LOGS/git-curl.log" 2>/dev/null || true
  exit "$rc"
fi
git -C "$SRC/$TARGET" rev-parse --verify HEAD | tee -a "$LOGS/final-status.txt"
{
  echo '### Official public TWRP16 Clang source-only checkout: SUCCESS'
  cat "$LOGS/final-status.txt"
} >> "$GITHUB_STEP_SUMMARY"
