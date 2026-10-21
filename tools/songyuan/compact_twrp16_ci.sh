#!/usr/bin/env bash
set -euo pipefail
TOP="${1:?source root required}"
LOGS="${2:?log dir required}"
: "${GITHUB_WORKSPACE:?}" "${RUNNER_TEMP:?}" "${GITHUB_STEP_SUMMARY:?}"
[[ "$TOP" = /* && "$LOGS" = /* ]] || exit 2
[[ ! -e "$TOP/.repo" && ! -e "$LOGS" ]] || exit 2
mkdir -p "$TOP" "$LOGS" "$RUNNER_TEMP/songyuan-bin"
CLANG=prebuilts/clang/host/linux-x86
SHA=2d4dcbff7cb42f360f368bacf51cfe711fd1cb0f
MIN_FREE_KIB=15728640
curl -fsSL --retry 3 https://storage.googleapis.com/git-repo-downloads/repo -o "$RUNNER_TEMP/songyuan-bin/repo"
chmod 0755 "$RUNNER_TEMP/songyuan-bin/repo"
export PATH="$RUNNER_TEMP/songyuan-bin:$PATH"
cd "$TOP"
repo init -u https://github.com/TWRP-Test/platform_manifest_twrp_aosp -b twrp-16.0 --depth=1 --partial-clone --clone-filter=blob:none > "$LOGS/repo-init.txt" 2>&1 || {
  tail -60 "$LOGS/repo-init.txt"; exit 21;
}
mkdir -p .repo/local_manifests
cat > .repo/local_manifests/songyuan-standalone-clang.xml <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <remove-project name="platform/prebuilts/clang/host/linux-x86" />
  <!-- Source patches and OMAPI contracts are audited against these exact upstream revisions. -->
  <extend-project name="android_bootable_recovery" path="bootable/recovery" revision="0315dbb53c47a0532546b7056f6af71b4dc0ddab" />
  <extend-project name="android_system_vold" path="system/vold" revision="4c83041ec61f9b482085685f1e6aed5a62f103aa" />
  <extend-project name="android_se_omapi" path="external/se_omapi" revision="4d1e09a8b18dc3e2bec644e50401e28ea695f3d1" />
</manifest>
XML
test -f .repo/manifests/README.md
grep -Fq 'ALLOW_MISSING_DEPENDENCIES=true' .repo/manifests/README.md || {
  echo "::error::Upstream minimal TWRP16 reduced-manifest build mode is no longer confirmed"
  exit 22
}
repo manifest -o "$LOGS/effective-391-projects.xml"
python3 - "$LOGS/effective-391-projects.xml" <<'PY'
import sys, xml.etree.ElementTree as E
from pathlib import Path
root=E.parse(sys.argv[1]).getroot()
p=[x.get('path') or x.get('name') for x in root.findall('project')]
required=['build/make','build/soong','bootable/recovery','system/vold','vendor/twrp']
if len(p)!=391 or len(set(p))!=391 or 'prebuilts/clang/host/linux-x86' in p or any(x not in p for x in required):
    raise SystemExit(f'FAIL-CLOSED: expected 391 actual upstream projects excluding pinned Clang; got {len(p)}; required missing={[x for x in required if x not in p]}')
expected_source_pins={
  'bootable/recovery':'0315dbb53c47a0532546b7056f6af71b4dc0ddab',
  'system/vold':'4c83041ec61f9b482085685f1e6aed5a62f103aa',
  'external/se_omapi':'4d1e09a8b18dc3e2bec644e50401e28ea695f3d1',
}
revisions={x.get('path') or x.get('name'): x.get('revision') for x in root.findall('project')}
bad={path: revisions.get(path) for path, rev in expected_source_pins.items()
     if revisions.get(path) != rev}
if bad:
    raise SystemExit(f'FAIL-CLOSED: audited TWRP16 source pin drift before 391-project sync: {bad}')
print('PASS: 3 upstream source commits locked before expensive TWRP16 sync')
print('PASS: upstream 391 projects with intact AOSP/TWRP16 required paths')
PY
# Source sync previously stopped on the upstream Bazel common checkout.
# Preflight that exact project serially BEFORE the expensive Clang/full sync.
BAZEL_COMMON='prebuilts/bazel/common'
echo 'Preflight original upstream Bazel common worktree serially'
if ! timeout --signal=TERM --kill-after=40s 1200s repo sync -v -c -j1 --no-interleaved \
  --jobs-network=1 --jobs-checkout=1 --retry-fetches=3 \
  --no-clone-bundle --no-tags --fail-fast "$BAZEL_COMMON" > "$LOGS/bazel-common-sync.log" 2>&1; then
  echo '::error::Bazel common source checkout failed before Clang/full source download'
  tail -n 120 "$LOGS/bazel-common-sync.log" || true
  exit 26
fi
test "$(git -C "$TOP/$BAZEL_COMMON" rev-parse --is-inside-work-tree)" = true
echo 'PASS: original Bazel common source checked out serially'
GCC_ROOT='prebuilts/gcc/linux-x86/host/x86_64-linux-glibc2.17-4.8'
echo 'Probing original Android16 GCC/glibc worktree before any expensive full sync'
if ! timeout --signal=TERM --kill-after=40s 1200s repo sync -v -c -j1 \
  --no-interleaved --jobs-network=1 --jobs-checkout=1 --retry-fetches=3 \
  --no-clone-bundle --no-tags --fail-fast "$GCC_ROOT" > "$LOGS/gcc-worktree-sync.log" 2>&1; then
  echo '::error::Original official Android16 GCC/glibc source checkout failed'
  tail -n 60 "$LOGS/gcc-worktree-sync.log" || true
  exit 23
fi
test -s "$TOP/$GCC_ROOT/Android.bp" || { echo '::error::Original GCC sysroot Android.bp absent'; exit 24; }
test "$(git -C "$TOP/$GCC_ROOT" rev-parse HEAD)" = ed661b61b5f6d657500fc97d485edd35b2cb3c7f || {
  echo '::error::Original GCC sysroot differs from pinned Android16 r1 source'; exit 25;
}
echo 'PASS: exact original AOSP16 glibc/GCC worktree checked out serially'
bash "$GITHUB_WORKSPACE/tools/songyuan/probe_clang_sparse.sh"
mkdir -p "$(dirname "$TOP/$CLANG")"
mv "$RUNNER_TEMP/songyuan-clang-sparse" "$TOP/$CLANG"
test "$(git -C "$TOP/$CLANG" rev-parse HEAD)" = "$SHA"
test -s "$TOP/$CLANG/Android.bp"
grep -Fq 'name: "libclang_rt.builtins",' "$TOP/$CLANG/Android.bp"
test -s "$TOP/$CLANG/clang-r547379/lib/clang/20/lib/linux/libclang_rt.builtins-aarch64-android.a"
test -x "$TOP/$CLANG/clang-r547379/bin/clang"
test -x "$TOP/$CLANG/clang-r530567/bin/clang"
test -x "$TOP/$CLANG/clang-r530567/bin/clang.real"
test -s "$TOP/$CLANG/clang-r530567/lib/libclang.so"
test -s "$TOP/$CLANG/clang-r530567/lib/libLLVM.so"
readelf -h "$TOP/$CLANG/clang-r530567/lib/libclang.so" | grep -q 'Advanced Micro Devices X86-64'
if LD_LIBRARY_PATH="$TOP/$CLANG/clang-r530567/lib:${LD_LIBRARY_PATH:-}" \
    ldd "$TOP/$CLANG/clang-r530567/lib/libclang.so" | grep -F 'not found'; then
  echo "::error::Original r530567 Rust bindgen libclang has missing runtime"; exit 29;
fi
if LD_LIBRARY_PATH="$TOP/$CLANG/clang-r530567/lib:${LD_LIBRARY_PATH:-}" \
    ldd "$TOP/$CLANG/clang-r530567/bin/clang.real" | grep -F 'not found'; then
  echo "::error::Original r530567 clang.real has missing runtime"; exit 32;
fi
printf '%s\t%s\n' "$CLANG" "$SHA" > "$LOGS/standalone-clang-revision.tsv"
df -hT "$TOP" | tee "$LOGS/after-clang-disk.txt"
echo "start 391-project upstream source sync with 15GiB disk watchdog"
# Current git-repo defaults to interleaved, in which --jobs-checkout
# and --jobs-network are IGNORED; explicitly run phased fetch/checkout.
setsid timeout --signal=TERM --kill-after=40s 15000s repo --trace sync -v -c -j2 --no-interleaved --jobs-network=2 --jobs-checkout=1 --retry-fetches=3 --no-clone-bundle --no-tags --fail-fast > "$LOGS/repo-sync.log" 2>&1 &
pid=$!
killed=0
while kill -0 "$pid" 2>/dev/null; do
  sleep 15
  free_kib="$(df -Pk "$TOP" | awk 'END{print $4}')"
  used_kib="$(df -Pk "$TOP" | awk 'END{print $3}')"
  printf '%s\t%s\t%s\n' "$(date +%s)" "$free_kib" "$used_kib" >> "$LOGS/disk-heartbeat.tsv"
  if (( free_kib < MIN_FREE_KIB )); then
    echo "::error::391-source sync exceeded allowed space; stopping without AOSP compile"
    kill -TERM -- "-$pid" 2>/dev/null || true
    killed=1
    break
  fi
done
rc=0
wait "$pid" || rc=$?
if (( killed )); then rc=99; fi
# One bounded serial recovery if original checkout init failed, never for a
# disk-watchdog kill. Keep all 391 original source projects and exact pins.
if (( rc != 0 && rc != 99 )) && grep -Fq 'Cannot initialize work tree' "$LOGS/repo-sync.log"; then
  free_kib="$(df -Pk "$TOP" | awk 'END {print $4}')"
  if (( free_kib >= 31457280 )); then
    echo '::warning::Retry original source checkout ONCE in serial mode'
    if timeout --signal=TERM --kill-after=40s 3600s repo --trace sync -v -c -j1 --no-interleaved \
      --jobs-network=1 --jobs-checkout=1 --retry-fetches=3 \
      --no-clone-bundle --no-tags --fail-fast > "$LOGS/repo-sync-serial-retry.log" 2>&1; then
      echo 'PASS: 391 original upstream source projects recovered in serial mode'
      rc=0
    else
      rc=1
      echo '::error::Serial source sync recovery also failed'
      tail -n 120 "$LOGS/repo-sync-serial-retry.log" || true
    fi
  fi
fi
df -hT "$TOP" | tee "$LOGS/after-repo-sync-disk.txt"
if (( rc != 0 )); then
  echo "::error::391-source Repo sync failed (exit=$rc)"
  {
    echo "incomplete_repo_sync_exit=$rc"
    printf 'disk_summary\n'
    df -hT "$TOP"
    printf 'major_source_directories\n'
    du -sh "$TOP/.repo" "$TOP/prebuilts" "$TOP/external" "$TOP/frameworks" "$TOP/packages" "$TOP/system" "$TOP/build" 2>/dev/null || true
    printf 'project_git_directories_seen\n'
    find "$TOP/.repo/projects" -name '*.git' -type d -print 2>/dev/null | wc -l
    printf 'repo_log_size\n'
    wc -c "$LOGS/repo-sync.log"
  } > "$LOGS/incomplete-source-inventory.txt"
  python3 - "$LOGS/repo-sync.log" <<'PY'
import re, sys
from pathlib import Path
lines = Path(sys.argv[1]).read_text(errors='replace').splitlines()
pattern = re.compile(r'fatal:|error\.GitError|Cannot initialize work tree|read-tree|missing blob|fetch-pack|unable to|failed to|permission denied|operation must be run|unpack tree', re.I)
hits = [i for i, line in enumerate(lines) if pattern.search(line)]
chosen = set()
for i in hits[-40:]:
    chosen.update(range(max(0, i-3), min(len(lines), i+4)))
print(f'PUBLIC-UPSTREAM-SOURCE-SYNC-ERROR-CONTEXT: {len(hits)} diagnostic lines matched')
for i in sorted(chosen):
    text = lines[i]
    text = re.sub(r'(?i)(https?://)[^/@\s]+:[^/@\s]+@', r'\1[REDACTED]@', text)
    print(f'  L{i+1}: {text[:600]}')
PY
  # Capture underlying git read-tree stderr, not just Repo's wrapper.
  if [[ -s "$LOGS/repo-sync-serial-retry.log" ]]; then
    echo 'SERIAL-RETRY-ROOT-ERRORS:'
    grep -iEn -C 3 'fatal:|error:|read-tree|missing blob|http.*[45][0-9][0-9]|cannot initialize work tree|failed to' "$LOGS/repo-sync-serial-retry.log" | tail -n 140 || true
  fi
  tail -120 "$LOGS/repo-sync.log" || true
  exit 31
fi
repo manifest -r -o "$LOGS/resolved-391-projects.xml"
python3 - "$TOP" "$LOGS/resolved-391-projects.xml" "$LOGS/392-verified-source-revisions.tsv" "$CLANG" "$SHA" <<'PY'
import subprocess, sys, xml.etree.ElementTree as E
from pathlib import Path
top=Path(sys.argv[1])
p=[x.get('path') or x.get('name') for x in E.parse(sys.argv[2]).getroot().findall('project')]
if len(p)!=391 or len(set(p))!=391:
    raise SystemExit('wrong 391-project manifest')
rows=[]
for path in p:
    if not (top/path).is_dir(): raise SystemExit(f'missing checked-out source: {path}')
    rev=subprocess.check_output(['git','-C',str(top/path),'rev-parse','HEAD'],text=True).strip()
    if len(rev)!=40: raise SystemExit('invalid source revision '+path)
    rows.append((path,rev))
compiler_path,compiler_sha=sys.argv[4:]
if compiler_path in p: raise SystemExit('duplicate original clang project')
actual=subprocess.check_output(['git','-C',str(top/compiler_path),'rev-parse','HEAD'],text=True).strip()
if actual!=compiler_sha: raise SystemExit('original clang checkout mutated')
rows.append((compiler_path,actual))
if len(set(x[0] for x in rows))!=392: raise SystemExit('392 source projects not complete')
Path(sys.argv[3]).write_text(''.join(f'{path}\t{sha}\n' for path,sha in sorted(rows)))
print('PASS: original TWRP16 391 project commits + 1 pinned original AOSP Clang = 392 exact source revisions')
PY
(cd "$LOGS"; sha256sum effective-391-projects.xml resolved-391-projects.xml 392-verified-source-revisions.tsv standalone-clang-revision.tsv > SOURCE-SHA256SUMS.txt; sha256sum -c SOURCE-SHA256SUMS.txt)
df -hT "$TOP" | tee "$LOGS/final-source-disk.txt"
du -sh "$TOP" "$TOP/$CLANG" "$TOP/.repo" | tee "$LOGS/source-sizes.txt"
echo "392 original TWRP16 source projects verified; compiled ELF still not built" >> "$GITHUB_STEP_SUMMARY"
