#!/usr/bin/env bash
set -euo pipefail
[[ "$#" -eq 1 ]] || exit 2
root="$(cd "$1" && pwd)/bootable/recovery"
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/patches/recovery"
test -d "$root" && test -d "$dir"
for name in 0002-super.patch 0003-storage.patch; do
    patch="$dir/$name"
    test -s "$patch"
    git -C "$root" apply --check "$patch"
    git -C "$root" apply "$patch"
done
