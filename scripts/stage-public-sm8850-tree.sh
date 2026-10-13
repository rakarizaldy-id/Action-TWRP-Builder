#!/usr/bin/env bash
# Only stage publicly released YuKongA SM8850 tree.
# Does not build Android, touch recovery images, or fetch OEM/private data.
set -euo pipefail
if (( $# != 2 )); then
  echo "Usage: bash $0 PUBLIC_TREE_DIR DEST_DEVICE_TREE_DIR" >&2
  exit 2
fi
from="$1"
dest="$2"
[[ "$from" = /* && "$dest" = /* ]] || {
  echo "::error::Tree source and destination must be absolute paths."
  exit 2
}
test -d "$from" || { echo "::error::Public source tree not found"; exit 3; }
for required in BoardConfig.mk AndroidProducts.mk twrp_sm8850.mk prebuilt/kernel; do
  test -s "$from/$required" || {
    echo "::error::Public SM8850 prerequisite missing: $required"
    exit 4
  }
done
test ! -e "$dest" || {
  echo "::error::Refusing to overwrite existing device tree: $dest"
  exit 5
}
# A fresh TWRP manifest does NOT necessarily contain device/xiaomi.
# This must be done BEFORE the copy; previously 74G source sync was wasted here.
mkdir -p -- "$(dirname "$dest")"
cp -a -- "$from" "$dest"
test -s "$dest/BoardConfig.mk"
test -s "$dest/prebuilt/kernel"
cmp -s "$from/BoardConfig.mk" "$dest/BoardConfig.mk"
cmp -s "$from/prebuilt/kernel" "$dest/prebuilt/kernel"
echo "PASS: Public SM8850 device tree staged with verified parent dirs: $dest"
