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
# Bash nounset incompatible with AOSP envsetup. No -j override, no image.
set +u
source build/envsetup.sh
export ALLOW_MISSING_DEPENDENCIES=true
lunch twrp_songyuan
test "${TARGET_PRODUCT:-}" = twrp_songyuan
set -u
m recovery 2>&1 | tee "$logs/m-recovery-songyuan.log"
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
echo 'PASS: twrp_songyuan m recovery binary-only (untested OEM integration)'
