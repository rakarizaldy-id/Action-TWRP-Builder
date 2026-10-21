#!/usr/bin/env bash
set -euo pipefail
if [[ "$#" -ne 3 ]]; then
 echo "Usage: prepare.sh /path/to/TWRP16 /path/to/verified-ID305-OEM /path/to/standalone-Songyuan-DT" >&2;exit 2
fi
TOP="$(cd "$1" && pwd)"
OEM="$(cd "$2" && pwd)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TREE="$(cd "$3" && pwd)"
DEST="$TOP/device/xiaomi/songyuan"
test -f "$TOP/build/envsetup.sh" || { echo "FAIL: TWRP16 source missing";exit 3; }
test -f "$TREE/BoardConfig.mk" || { echo "FAIL: first-party Songyuan tree missing";exit 3; }
test "$TREE" != "$DEST" || { echo "FAIL: source tree must be outside target TWRP checkout";exit 3; }
test ! -e "$DEST" || { echo "FAIL: destination exists; refuse overwriting";exit 3; }
python3 "$HERE/verify_oem.py" "$OEM"
python3 "$HERE/validate_clean.py" "$TREE"
stage="$(mktemp -d "$TOP/.songyuan-clean-XXXXXXXX")"
trap 'rm -rf "$stage"' EXIT
rsync -a --exclude=".git/" "$TREE/" "$stage/"
python3 "$HERE/verify_oem.py" "$stage/prebuilt"
for binroot in "$stage/prebuilt/vendor/bin" "$stage/prebuilt/odm/bin"; do
  if [[ -d "$binroot" ]]; then
    find "$binroot" -type f -exec chmod 0755 {} +
  fi
done
python3 "$HERE/validate_clean.py" "$stage" --staged
python3 - "$TOP/external/se_omapi/Android.bp" "$TOP/external/se_omapi/se_omapi.rc" <<'PY'
from pathlib import Path
import sys
bp, rc = map(Path, sys.argv[1:])
if not bp.is_file() or not rc.is_file():
    raise SystemExit("FAIL: official external/se_omapi sources are missing")
source, service = bp.read_text(), rc.read_text()
required = ('name: "se_omapi"', 'init_rc: ["se_omapi.rc"]',
            'vintf_fragments: ["se_omapi.xml"]', 'recovery_available: true')
if not all(text in source for text in required):
    raise SystemExit("FAIL: upstream OMAPI Soong module or recovery init_rc drifted")
if (service.count("service se_omapi /system/bin/se_omapi") != 1
    or "on late-init\n    start se_omapi\n" not in service
    or "android.se.omapi.ISecureElementService/default" not in service):
    raise SystemExit("FAIL: official TWRP16 OMAPI late-init/AIDL contract drifted")
print("PASS: upstream OMAPI single init_rc/Soong producer unchanged")
PY
# Soong retains sole ownership of init.recovery.usb.rc; stage EXACT
# native Songyuan configfs contents into its already-defined source input.
usb_bp="$TOP/bootable/recovery/etc/Android.bp"
usb_soong_src="$TOP/bootable/recovery/etc/init.recovery.usb.rc"
usb_native_src="$stage/usb/init.recovery.usb.rc"
test -s "$usb_bp" && test -s "$usb_soong_src" && test -s "$usb_native_src"
grep -Fq 'name: "init.recovery.usb.rc"' "$usb_bp"
grep -Fq 'src: "init.recovery.usb.rc"' "$usb_bp"
grep -Fq 'install_in_root: true' "$usb_bp"
grep -Fq '/config/usb_gadget/g1' "$usb_native_src"
! grep -Fq '/sys/class/android_usb/android0' "$usb_native_src"
cp -- "$usb_native_src" "$usb_soong_src"
cmp -s "$usb_native_src" "$usb_soong_src"
mkdir -p "$(dirname "$DEST")"
mv "$stage" "$DEST"
echo "PASS: original Songyuan USB bytes staged for sole upstream Soong writer"
