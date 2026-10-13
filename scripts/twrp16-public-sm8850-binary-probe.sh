#!/usr/bin/env bash
# PUBLIC TWRP16 compilation smoke test with PUBLIC YuKongA SM8850 tree.
# This is NOT the Songyuan-specific/private-ID305 binary.
# NEVER fetch, embed, or upload proprietary/private Songyuan OEM here.
set -euo pipefail
: "${GITHUB_WORKSPACE:?}" "${RUNNER_TEMP:?}"
SRC="$GITHUB_WORKSPACE/twrp"
LOGS="$RUNNER_TEMP/twrp16-sm8850-public-binary"
OUT="$RUNNER_TEMP/twrp16-sm8850-public-binary-out"
MIN_FREE_KIB=15728640  # 15 GiB watchdog during compilation
mkdir -p "$LOGS" "$OUT"
echo "Compile experiment: PUBLIC YuKongA twrp_sm8850, m recovery, no Songyuan OEM/stock/image."
echo "Required build diagnostic tools:"
for tool in bash git python3 readelf awk timeout setsid df; do
  command -v "$tool" || { echo "::error::Missing required tool: $tool"; exit 10; }
done
echo "Memory at build start:"
free -h
cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.events 2>/dev/null || true
test -f "$SRC/build/envsetup.sh"
test -d "$SRC/vendor/twrp"
test ! -e "$SRC/device/xiaomi/songyuan"
test ! -e "$GITHUB_WORKSPACE/.songyuan-oem"
cd "$SRC"
TREE="device/xiaomi/sm8850"
if [[ -e "$TREE" ]]; then
  echo "::error::Unexpected device tree already present; refuse overwrite"
  exit 30
fi
# Public tree was cloned and inspected BEFORE the 74G sync.
# Reuse that exact source instead of cloning/checking unknown files late.
test -s "$RUNNER_TEMP/public-sm8850-tree/prebuilt/kernel" || {
  echo "::error::Public YuKongA preflight tree missing"
  exit 31
}
cp -a "$RUNNER_TEMP/public-sm8850-tree" "$TREE"
git -C "$TREE" rev-parse HEAD | tee "$LOGS/public-device-tree-SHA.txt"
df -hT "$SRC" | tee "$LOGS/before-build-disk.txt"

# Compile the recovery binary target, NOT an Android recovery partition image.
# No -j override, following the user's explicit build target instructions.
started="$SECONDS"
setsid timeout --signal=TERM --kill-after=40s 14400s \
  bash -c '
    set -eo pipefail
    test -s build/envsetup.sh
    echo "CHECKPOINT: AOSP envsetup begin"
    source build/envsetup.sh
    echo "CHECKPOINT: AOSP envsetup PASS"
    export ALLOW_MISSING_DEPENDENCIES=true
    echo "CHECKPOINT: lunch twrp_sm8850 begin"
    lunch twrp_sm8850
    echo "CHECKPOINT: lunch PASS; TARGET_PRODUCT=${TARGET_PRODUCT:-unset}"
    test "${TARGET_PRODUCT:-}" = twrp_sm8850
    echo "CHECKPOINT: m recovery begin (no -j, no image)"
    m recovery
    echo "CHECKPOINT: m recovery PASS"
  ' > "$LOGS/m-recovery-build.log" 2>&1 &
pid="$!"
checks=0
disk_stop=0
rc=0
printf 'epoch\telapsed_seconds\tfree_kib\tmem_available_kib\tswap_free_kib\tcgroup_oom_kill\n' > "$LOGS/disk-heartbeat.tsv"
while kill -0 "$pid" 2>/dev/null; do
  sleep 20
  checks=$((checks+1))
  free_kib="$(df -Pk "$SRC" | awk 'END {print $4}')"
  mem_avail_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
  swap_free_kib="$(awk '/^SwapFree:/ {print $2}' /proc/meminfo)"
  cgroup_oom_kill="$(awk '/^oom_kill / {print $2}' /sys/fs/cgroup/memory.events 2>/dev/null || printf 0)"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(date +%s)" "$((SECONDS-started))" \
    "$free_kib" "$mem_avail_kib" "$swap_free_kib" "$cgroup_oom_kill" \
    >> "$LOGS/disk-heartbeat.tsv"
  if (( checks%3==0 )); then
    echo "BUILD-HEARTBEAT: elapsed=$((SECONDS-started))s free_kib=$free_kib mem_avail_kib=$mem_avail_kib swap_free_kib=$swap_free_kib oom_kill=$cgroup_oom_kill"
    echo "BUILD-HEARTBEAT: last 12 compile log lines:"
    tail -n 12 "$LOGS/m-recovery-build.log" || true
    echo "BUILD-HEARTBEAT: cgroup memory and CPU pressure:"
    cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.max /proc/pressure/memory 2>/dev/null || true
  fi
  if (( free_kib < MIN_FREE_KIB )); then
    echo "::error::Low disk during m recovery; stopped before crossing 15 GiB free."
    kill -TERM -- "-$pid" 2>/dev/null || true
    disk_stop=1
    break
  fi
done
wait "$pid" || rc=$?
if (( disk_stop )); then rc=99; fi
printf 'exit_code=%s\nelapsed_seconds=%s\n' "$rc" "$((SECONDS-started))" \
  | tee "$LOGS/build-result.txt"
df -hT "$SRC" | tee "$LOGS/after-build-disk.txt"
if (( rc != 0 )); then
  echo "::error::PUBLIC YuKongA m recovery failed (exit_code=$rc)"
  tail -n 120 "$LOGS/m-recovery-build.log" || true
  exit "$rc"
fi

product="$SRC/out/target/product/sm8850"
src=""
for candidate in \
  "$product/recovery/root/system/bin/recovery" \
  "$product/recovery/root/sbin/recovery" \
  "$product/obj/EXECUTABLES/recovery_intermediates/recovery" \
  "$product/system/bin/recovery"; do
  if [[ -s "$candidate" ]] && readelf -h "$candidate" 2>/dev/null | grep -qE 'Machine:.*AArch64'; then
    src="$candidate"
    break
  fi
done
if [[ -z "$src" ]]; then
  while IFS= read -r candidate; do
    if readelf -h "$candidate" 2>/dev/null | grep -qE 'Machine:.*AArch64'; then
      src="$candidate"
      break
    fi
  done < <(find "$SRC/out/soong/.intermediates/bootable/recovery" "$product" \
    -type f -name recovery -print 2>/dev/null | sort -u || true)
fi
if [[ -z "$src" ]]; then
  echo "::error::m recovery returned success but AArch64 recovery executable is missing."
  find "$product" -maxdepth 7 -name '*recovery*' -print 2>/dev/null | head -80 || true
  exit 33
fi
cp -p "$src" "$OUT/recovery"
printf '%s\n' "$src" > "$OUT/BINARY-PATH.txt"
readelf -h "$OUT/recovery" > "$OUT/ELF-HEADER.txt"
readelf -d "$OUT/recovery" > "$OUT/ELF-NEEDED.txt" 2>&1 || true
sha256sum "$OUT/recovery" > "$OUT/SHA256SUMS"
if [[ -d "$product/recovery/root" ]]; then
  find "$product/recovery/root" -type f -printf '%P\n' | sort \
    > "$OUT/RUNTIME-CANDIDATE-FILE-PATHS.txt"
fi
cat > "$OUT/NOTICE-UNTESTED.txt" <<'EOF'
PUBLIC YuKongA SM8850 TWRP16 recovery executable BUILD EXPERIMENT.
This is NOT a Songyuan-specific OEM ID305 build and is NOT a recovery.img.
The executable alone is not bootable/flashable or verified against Songyuan stock.
Never flash it or interpret this as proof of stock replacement compatibility.
No Songyuan private OEM, phone, userdata, or stock image was used in this job.
EOF
test ! -e "$product/recovery.img" || {
  echo "::error::Unexpected recovery.img appeared despite m recovery-only compile"
  exit 34
}
{
  echo "### SUCCESS: public YuKongA generic SM8850 m recovery binary"
  echo "No Songyuan OEM; no recovery.img; generic compilation proof only."
  cat "$LOGS/build-result.txt" "$LOGS/after-build-disk.txt"
} >> "$GITHUB_STEP_SUMMARY"
echo "Public generic recovery ELF SHA256: $(sha256sum "$OUT/recovery")"
