#!/usr/bin/env bash
# Intended solely for GitHub Actions public runner. NEVER run on user's laptop.
set -euo pipefail
: "${GITHUB_WORKSPACE:?}" "${RUNNER_TEMP:?}"
root="$GITHUB_WORKSPACE/twrp"
tree="$GITHUB_WORKSPACE/device/xiaomi/songyuan"
target="$root/device/xiaomi/songyuan"
out="$RUNNER_TEMP/songyuan-public-binary-output"
logs="$RUNNER_TEMP/songyuan-public-build-logs"
mkdir -p "$out" "$logs" "$(dirname "$target")"
test ! -e "$target"
test ! -e "$GITHUB_WORKSPACE/.songyuan-oem"
test ! -e "$GITHUB_WORKSPACE/boot.img"
test ! -e "$GITHUB_WORKSPACE/recovery.img"
python3 "$GITHUB_WORKSPACE/scripts/validate-songyuan-source-only.py" "$tree"
cp -a -- "$tree" "$target"
python3 "$GITHUB_WORKSPACE/scripts/validate-songyuan-source-only.py" "$target"
cd "$root"
# Source envsetup and invoke lunch/m recovery in a separate shell: never -u.
# Bounded time, disk watchdog and complete logs; GitHub compiles ELF ONLY.
phase=compile
setsid timeout --signal=TERM --kill-after=40s 14400s bash -c '
  set -eo pipefail
  source build/envsetup.sh
  export ALLOW_MISSING_DEPENDENCIES=true
  echo "CHECKPOINT: lunch twrp_songyuan"
  lunch twrp_songyuan
  test "${TARGET_PRODUCT:-}" = twrp_songyuan
  echo "CHECKPOINT: lunch PASS; m recovery begins"
  m recovery
  echo "CHECKPOINT: m recovery PASS"
' > "$logs/full-lunch-and-build.log" 2>&1 &
pid=$!
started=$SECONDS
checks=0
exit_code=0
printf 'epoch\telapsed_s\tfree_kib\tmem_available_kib\tcgroup_oom_kill\n' > "$logs/build-heartbeat.tsv"
while kill -0 "$pid" 2>/dev/null; do
  sleep 20
  checks=$((checks+1))
  free_kib="$(df -Pk "$root" | awk 'END{print $4}')"
  mem_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
  oom_kills="$(awk '/^oom_kill / {print $2}' /sys/fs/cgroup/memory.events 2>/dev/null || echo 0)"
  printf '%s\t%s\t%s\t%s\t%s\n' "$(date +%s)" "$((SECONDS-started))" "$free_kib" "$mem_kib" "$oom_kills" >> "$logs/build-heartbeat.tsv"
  if (( checks % 3 == 0 )); then
    echo "SONGYUAN-BUILD elapsed=$((SECONDS-started)) free_kib=$free_kib"
    tail -n 12 "$logs/full-lunch-and-build.log" || true
  fi
  if (( free_kib < 15728640 )); then
    echo "::error::Disk below 15GiB during Songyuan compile; terminating process group"
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    exit_code=99
    break
  fi
done
if wait "$pid"; then :; else result=$?; if (( exit_code == 0 )); then exit_code=$result; fi; fi
printf 'build_exit_code=%s\nelapsed_s=%s\n' "$exit_code" "$((SECONDS-started))" > "$logs/build-status.txt"
df -hT "$root" > "$logs/build-final-disk.txt" 2>&1 || true
if (( exit_code != 0 )); then
  echo "::error::lunch/m recovery failed, code=$exit_code"
  tail -n 120 "$logs/full-lunch-and-build.log"
  exit "$exit_code"
fi
product="$root/out/target/product/songyuan"
src=""
for p in "$product/recovery/root/system/bin/recovery" "$product/recovery/root/sbin/recovery" "$product/obj/EXECUTABLES/recovery_intermediates/recovery" "$product/system/bin/recovery"; do
 if [[ -s "$p" ]] && readelf -h "$p" 2>/dev/null | grep -q AArch64; then src="$p"; break; fi
done
if [[ -z "$src" ]]; then
 while IFS= read -r candidate; do
   if readelf -h "$candidate" 2>/dev/null | grep -q AArch64; then src="$candidate";break;fi
 done < <(find "$root/out/soong/.intermediates/bootable/recovery" "$product" -type f -name recovery -print 2>/dev/null || true)
fi
test -n "$src" || { echo 'AArch64 recovery executable not found'; exit 44; }
cp -p "$src" "$out/recovery"
readelf -h "$out/recovery" > "$out/ELF-HEADER.txt"
readelf -d "$out/recovery" > "$out/ELF-NEEDED.txt"
sha256sum "$out/recovery" > "$out/SHA256SUMS"
python3 "$GITHUB_WORKSPACE/scripts/audit-songyuan-runtime.py" \
  "$out/recovery" "$product" "$root/out/soong/.intermediates" "$out"
# Unlike old generic run, INCLUDE ACTUAL COMPATIBLE TWRP runtime file bytes.
# These are only public TWRP/AOSP outputs (no OEM files). No image is built.
if [[ -d "$product/recovery/root" ]]; then
  tar -C "$product/recovery" -czf "$out/TWRP-SOURCE-RUNTIME.tar.gz" root
  (cd "$product/recovery/root" && find . -type f | sort) > "$out/RUNTIME-FILE-INVENTORY.txt"
else
  echo 'WARNING: m recovery did not populate recovery/root; library closure unproven' > "$out/RUNTIME-WARNING.txt"
fi
cat > "$out/NOTICE-NOT-FLASHABLE.txt" <<'NOTICE'
POCO F9 Ultra (songyuan) Android 16 source-only TWRP compile probe.
No OEM kernel, HAL, KeyMint, ODM, vendor blobs or stock recovery image included.
This is not proof of a complete device-specific runtime, boot or FBE decrypt.
Stock ID305 replacement/repack is to be done IN CHAT ONLY after file-by-file audit.
NOTICE
test ! -e "$product/recovery.img" || { echo 'Unexpected image target output'; exit 45; }
echo 'PASS: twrp_songyuan ELF built; see RUNTIME-CLOSURE-STATUS.txt for missing libraries and linker. NOT FLASHABLE.'
