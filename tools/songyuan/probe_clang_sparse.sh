#!/usr/bin/env bash
set -euo pipefail
: "$RUNNER_TEMP" "$GITHUB_STEP_SUMMARY"
UPSTREAM='https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86'
TAG='android-16.0.0_r1'
EXPECTED_SHA='2d4dcbff7cb42f360f368bacf51cfe711fd1cb0f'
CLANG_VERSION='clang-r547379'
BINDGEN_CLANG_VERSION='clang-r530567'
ROOT="$RUNNER_TEMP/songyuan-clang-sparse"
LOGDIR="$RUNNER_TEMP/songyuan-clang-probe"
RESERVE_KIB=15728640
mkdir -p "$LOGDIR"
test ! -e "$ROOT" || { echo "::error::Probe requires fresh root"; exit 2; }
printf 'official_remote=%s\ntag=%s\nexpected_sha=%s\ncompiler=%s\nno_oem=true\nno_full_sync=true\nno_build=true\n'   "$UPSTREAM" "$TAG" "$EXPECTED_SHA" "$CLANG_VERSION" > "$LOGDIR/PROBE-PROVENANCE.txt"
df -hT "$RUNNER_TEMP" | tee "$LOGDIR/disk-before.txt"
git --version | tee "$LOGDIR/git-version.txt"
sudo rm -rf /usr/local/lib/android /usr/share/dotnet /usr/local/share/powershell /usr/local/.ghcup /opt/ghc /usr/share/swift /opt/hostedtoolcache
sudo apt-get clean
df -hT "$RUNNER_TEMP" | tee "$LOGDIR/disk-after-cleanup.txt"
free_kib="$(df -Pk "$RUNNER_TEMP" | awk 'END {print $4}')"
if (( free_kib < 18874368 )); then
  echo "::error::Post-cleanup disk less than 18GiB free; abort before Clang fetch"
  exit 20
fi
echo "## TWRP16 original AOSP Clang selective-checkout PROBE (not a build)" >> "$GITHUB_STEP_SUMMARY"
refs="$(git ls-remote "$UPSTREAM" "refs/tags/$TAG" "refs/tags/$TAG^{}")"
observed="$(printf '%s\n' "$refs" | awk '$2 ~ /\^\{\}$/ { peeled=$1 } $2 !~ /\^\{\}$/ && first=="" { first=$1 } END { print peeled!="" ? peeled : first }')"
printf 'tag_sha=%s\n' "$observed" >> "$LOGDIR/PROBE-PROVENANCE.txt"
if [[ "$observed" != "$EXPECTED_SHA" ]]; then
  echo "::error::AOSP release tag does not match proven Clang SHA from run 38933673078."
  printf 'tag=%s expected=%s\n' "$observed" "$EXPECTED_SHA"
  exit 21
fi
run_guarded() {
  local label="$1" limit="$2" code=0 low=0 elapsed=0
  shift 2
  setsid timeout --signal=TERM --kill-after=20s "$limit"s "$@" > "$LOGDIR/$label.log" 2>&1 &
  local pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    sleep 10
    elapsed=$((elapsed+10))
    local free_kib
    free_kib="$(df -Pk "$RUNNER_TEMP" | awk 'END {print $4}')"
    if (( elapsed % 60 == 0 )); then
      printf 'clang_stage=%s elapsed=%ss free_gib=%s cached_objects=' "$label" "$elapsed" "$((free_kib/1048576))"
      du -sh "$ROOT/.git/objects" 2>/dev/null | awk '{print $1}' || true
    fi
    printf '%s %s %s\n' "$(date +%s)" "$label" "$free_kib" >> "$LOGDIR/free-disk-heartbeat.txt"
    if (( free_kib < RESERVE_KIB )); then
      echo "::error::$label breached 15GiB free disk reserve"
      kill -TERM -- "-$pid" 2>/dev/null || true
      low=1
      break
    fi
  done
  wait "$pid" || code=$?
  if (( low )); then code=99; fi
  printf '%s exit=%s\n' "$label" "$code" >> "$LOGDIR/stage-status.txt"
  df -hT "$RUNNER_TEMP" > "$LOGDIR/disk-after-$label.txt"
  if (( code != 0 )); then
    echo "::error::Stage $label failed (exit $code)"
    tail -n 40 "$LOGDIR/$label.log" || true
  fi
  return "$code"
}
git init -q "$ROOT"
git -C "$ROOT" remote add origin "$UPSTREAM"
git -C "$ROOT" sparse-checkout init --no-cone
git -C "$ROOT" sparse-checkout set --no-cone \
  "/Android.bp" \
  "/$CLANG_VERSION/" \
  "/clang-stable/" "/llvm-binutils-stable/" "/soong/" \
  "/$BINDGEN_CLANG_VERSION/bin/" \
  "/$BINDGEN_CLANG_VERSION/lib/"
run_guarded fetch 720 git -C "$ROOT" -c protocol.version=2 fetch --depth=1 --filter=blob:none --no-tags origin "$EXPECTED_SHA"
test "$(git -C "$ROOT" rev-parse FETCH_HEAD)" = "$EXPECTED_SHA"
git help -a | grep -E '(^|[[:space:]])backfill([[:space:]]|$)' >/dev/null || {
  echo "::error::Git >=2.49 with git backfill required for batched pinned AOSP Clang download"
  exit 34
}
run_guarded index 120 git -C "$ROOT" reset --mixed "$EXPECTED_SHA"
run_guarded backfill 1500 git -C "$ROOT" -c protocol.version=2 backfill --no-sparse --min-batch-size=512 "$EXPECTED_SHA" --   Android.bp "$CLANG_VERSION" clang-stable llvm-binutils-stable soong   "$BINDGEN_CLANG_VERSION/bin" "$BINDGEN_CLANG_VERSION/lib"
for required in Android.bp   "$CLANG_VERSION/bin/clang"   "$CLANG_VERSION/lib/clang/20/lib/linux/libclang_rt.builtins-aarch64-android.a"   "$BINDGEN_CLANG_VERSION/bin/clang"   "$BINDGEN_CLANG_VERSION/bin/clang.real"   "$BINDGEN_CLANG_VERSION/lib/libclang.so"   "$BINDGEN_CLANG_VERSION/lib/libLLVM.so"; do
  GIT_NO_LAZY_FETCH=1 git -C "$ROOT" cat-file -e "$EXPECTED_SHA:$required" || {
    echo "::error::Batched first-party Clang missing required blob: $required"
    exit 35
  }
done
run_guarded materialize 300 env GIT_NO_LAZY_FETCH=1 git -C "$ROOT" reset --hard "$EXPECTED_SHA"
run_guarded checkout 60 env GIT_NO_LAZY_FETCH=1 git -C "$ROOT" checkout --detach "$EXPECTED_SHA"
test -s "$ROOT/Android.bp" || { echo "::error::Original root Clang Android.bp not staged"; exit 32; }
python3 - "$ROOT/Android.bp" <<'PY'
import re, sys
from pathlib import Path
bp = Path(sys.argv[1]).read_text()
for name in ('libclang_rt.builtins', 'libclang_rt.builtins-exported', 'libclang_rt.ubsan_minimal'):
    pat = r'libclang_rt_prebuilt_library_(?:static|shared)\s*\{\s*name:\s*"' + re.escape(name) + r'"'
    if not re.search(pat, bp):
        raise SystemExit(f"::error::Original Clang Android.bp missing Soong {name}")
print("PASS: official original compiler-rt Soong module definitions")
PY
test -s "$ROOT/$CLANG_VERSION/lib/clang/20/lib/linux/libclang_rt.builtins-aarch64-android.a" || {
  echo "::error::Original ARM64 compiler-rt builtins archive missing"; exit 33;
}
test -x "$ROOT/$CLANG_VERSION/bin/clang" || { echo "::error::Official main Clang executable absent"; exit 23; }
test -x "$ROOT/$BINDGEN_CLANG_VERSION/bin/clang" || { echo "::error::Official Rust Bindgen Clang wrapper absent"; exit 24; }
test -x "$ROOT/$BINDGEN_CLANG_VERSION/bin/clang.real" || { echo "::error::Official Rust Bindgen Clang real executable absent"; exit 30; }
test -s "$ROOT/$BINDGEN_CLANG_VERSION/lib/libclang.so" || { echo "::error::Original Rust Bindgen libclang.so absent"; exit 25; }
test -s "$ROOT/$BINDGEN_CLANG_VERSION/lib/libLLVM.so" || { echo "::error::Original Rust Bindgen libLLVM.so absent"; exit 26; }
readelf -h "$ROOT/$BINDGEN_CLANG_VERSION/lib/libclang.so" | grep -q 'Advanced Micro Devices X86-64' || {
  echo "::error::Original Bindgen libclang host ELF invalid"; exit 27;
}
"$ROOT/$CLANG_VERSION/bin/clang" --version | tee "$LOGDIR/compiler-version.txt"
"$ROOT/$BINDGEN_CLANG_VERSION/bin/clang" --version | tee "$LOGDIR/bindgen-clang-version.txt"
"$ROOT/$BINDGEN_CLANG_VERSION/bin/clang.real" --version | tee "$LOGDIR/bindgen-clang-real-version.txt"
if LD_LIBRARY_PATH="$ROOT/$BINDGEN_CLANG_VERSION/lib:${LD_LIBRARY_PATH:-}" \
    ldd "$ROOT/$BINDGEN_CLANG_VERSION/lib/libclang.so" | grep -F 'not found'; then
  echo "::error::Original Bindgen libclang has unresolved host dependencies"; exit 28;
fi
if LD_LIBRARY_PATH="$ROOT/$BINDGEN_CLANG_VERSION/lib:${LD_LIBRARY_PATH:-}" \
    ldd "$ROOT/$BINDGEN_CLANG_VERSION/bin/clang.real" | grep -F 'not found'; then
  echo "::error::Original Bindgen real compiler has unresolved host libraries"; exit 31;
fi
printf 'bindgen_compiler=%s\nbindgen_real=%s\nbindgen_library=%s\n' "$BINDGEN_CLANG_VERSION/bin/clang" "$BINDGEN_CLANG_VERSION/bin/clang.real" "$BINDGEN_CLANG_VERSION/lib/libclang.so" >> "$LOGDIR/PROBE-PROVENANCE.txt"
git -C "$ROOT" rev-parse HEAD > "$LOGDIR/checkout-sha.txt"
git -C "$ROOT" sparse-checkout list > "$LOGDIR/sparse-roots.txt"
git -C "$ROOT" count-objects -vH > "$LOGDIR/git-objects.txt"
du -sh "$ROOT" "$ROOT/$CLANG_VERSION" "$ROOT/$BINDGEN_CLANG_VERSION" "$ROOT/.git" | tee "$LOGDIR/sizes.txt"
df -hT "$RUNNER_TEMP" | tee "$LOGDIR/disk-after.txt"
{
 echo "AOSP Clang sparse checkout PASS at pinned SHA $EXPECTED_SHA"
 echo "This is only toolchain feasibility. 392-project Soong/TWRP build unverified."
 cat "$LOGDIR/sizes.txt" "$LOGDIR/disk-after.txt"
} >> "$GITHUB_STEP_SUMMARY"
echo "PROBE PASS: no OEM, no Android build, no recovery image"
