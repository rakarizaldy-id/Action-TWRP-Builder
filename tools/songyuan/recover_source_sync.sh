#!/usr/bin/env bash
# Recover only transient checkout failures of original manifest projects.
set -euo pipefail
TOP="${1:?TWRP source root required}"
LOGS="${2:?Source logs dir required}"
MANIFEST="${3:?391-project manifest required}"
: "${GITHUB_WORKSPACE:?}" "${RUNNER_TEMP:?}"
[[ "$TOP" = /* && "$LOGS" = /* ]] || exit 2
test -s "$MANIFEST"
cd "$TOP"
MIN_FREE_KIB=15728640
SAFE_RETRY_KIB=31457280
PARSER="$GITHUB_WORKSPACE/tools/songyuan/extract_failed_sync_projects.py"
test -s "$PARSER"

monitored() {
  local log="$1" limit="$2"; shift 2
  local pid rc=0 low=0 free_kib
  free_kib="$(df -Pk "$TOP" | awk 'END{print $4}')"
  if (( free_kib < MIN_FREE_KIB )); then
    echo "::error::Source sync below disk reserve"; return 99
  fi
  setsid timeout --signal=TERM --kill-after=40s "$limit"s "$@" > "$log" 2>&1 &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    sleep 15
    free_kib="$(df -Pk "$TOP" | awk 'END{print $4}')"
    printf '%s\t%s\t%s\n' "$(date +%s)" "$free_kib" "$log" >> "$LOGS/disk-heartbeat.tsv"
    if (( free_kib < MIN_FREE_KIB )); then
      echo "::error::Source sync breached disk reserve"
      kill -TERM -- "-$pid" 2>/dev/null || true
      low=1
      break
    fi
  done
  wait "$pid" || rc=$?
  if (( low )); then rc=99; fi
  return "$rc"
}

full=(repo --trace sync -v -c -j2 --no-interleaved
      --jobs-network=2 --jobs-checkout=1 --retry-fetches=3
      --no-clone-bundle --no-tags --fail-fast)
single=(repo sync -v -c -j1 --no-interleaved
        --jobs-network=1 --jobs-checkout=1 --retry-fetches=3
        --no-clone-bundle --no-tags --fail-fast)
rc=1
for round in 0 1 2; do
  log="$LOGS/repo-sync.log"
  if (( round > 0 )); then log="$LOGS/repo-sync-resume-$round.log"; fi
  limit=15000
  if (( round > 0 )); then limit=3600; fi
  echo "391-project source sync pass $((round+1))/3: preserve existing checkouts"
  if monitored "$log" "$limit" "${full[@]}"; then
    echo "PASS: all 391 original upstream project worktrees synced"
    exit 0
  else
    rc=$?
  fi
  if (( rc == 99 || round == 2 )); then break; fi
  failed="$LOGS/failed-projects-$round.txt"
  if ! python3 "$PARSER" "$log" "$MANIFEST" > "$failed"; then
    echo "::error::Source failure does not permit targeted retry"
    break
  fi
  mapfile -t projects < "$failed"
  if (( ${#projects[@]} == 0 )); then break; fi
  free_kib="$(df -Pk "$TOP" | awk 'END{print $4}')"
  if (( free_kib < SAFE_RETRY_KIB )); then
    echo "::error::Targeted retries require 30 GiB free disk"
    rc=99
    break
  fi
  repaired=1
  for project in "${projects[@]}"; do
    echo "::warning::Transient upstream HTTP transport; retry only $project"
    ok=0
    for attempt in 1 2 3; do
      sleep "$((15*attempt))"
      tag="${project//\//_}"
      part="$LOGS/targeted-$round-$tag-$attempt.log"
      if monitored "$part" 900 "${single[@]}" "$project"; then
        ok=1
        echo "PASS: targeted recovery $project"
        break
      else
        rc=$?
      fi
      if (( rc == 99 )); then break; fi
      grep -iE 'HTTP (429|5[0-9][0-9])|fatal:|Cannot checkout|Cannot initialize' "$part" | tail -n 12 || true
    done
    if (( ok == 0 )); then
      echo "::error::Targeted upstream checkout not recovered: $project"
      repaired=0
      break
    fi
  done
  if (( repaired == 0 )); then break; fi
  # Re-run incremental sync so all remaining 391 worktrees are checked out.
done
echo "::error::Full manifest sync incomplete; exit=$rc"
for log in "$LOGS"/repo-sync*.log "$LOGS"/targeted-*.log; do
  [[ -f "$log" ]] || continue
  echo "::group::$(basename "$log")"
  grep -iE 'HTTP (429|5[0-9][0-9])|fatal:|error\.GitError|Cannot checkout|Cannot initialize' "$log" | tail -n 16 || true
  echo "::endgroup::"
done
exit "$rc"
