#!/usr/bin/env python3
"""Fail closed if the USB or fstab install owner has drifted."""
from pathlib import Path
import re
import sys

if len(sys.argv) != 3:
    sys.exit("usage: verify_recovery_install_owners.py TWRP_ROOT STAGED_DT")
top, dt = map(Path, sys.argv[1:])
bp = (top / "bootable/recovery/Android.bp").read_text()
etc = (top / "bootable/recovery/etc/Android.bp").read_text()
soong = (top / "vendor/twrp/config/BoardConfigSoong.mk").read_text()
make = (top / "build/make/core/Makefile").read_text()
board = (dt / "BoardConfig.mk").read_text()
device = (dt / "device.mk").read_text()
native = dt / "usb/init.recovery.usb.rc"
staged = top / "bootable/recovery/etc/init.recovery.usb.rc"
if not native.is_file() or not staged.is_file() or native.is_symlink():
    sys.exit("BLOCKED: original Songyuan configfs USB input missing")
if staged.read_bytes() != native.read_bytes():
    sys.exit("BLOCKED: Soong USB input is not byte-exact Songyuan")
if b"/config/usb_gadget/g1" not in native.read_bytes():
    sys.exit("BLOCKED: native configfs USB syntax absent")
if b"/sys/class/android_usb/android0" in staged.read_bytes():
    sys.exit("BLOCKED: legacy USB payload detected")
if (dt / "recovery/root/init.recovery.usb.rc").exists():
    sys.exit("BLOCKED: recovery/root overlay still writes USB")
if "init.recovery.usb.rc" in device:
    sys.exit("BLOCKED: PRODUCT_COPY_FILES still writes USB")
if board.count("TW_EXCLUDE_DEFAULT_USB_INIT := false") != 1:
    sys.exit("BLOCKED: Soong recovery required module is disabled")
if not re.search(
    r'select\(soong_config_variable\("twrpGlobalVars",\s*"exclude_default_usb_init"\),\s*\{\s*false:\s*\[\s*"init\.recovery\.usb\.rc"',
    bp, re.S
):
    sys.exit("BLOCKED: upstream Soong required selector drifted")
if "exclude_default_usb_init, $(call twrp_scalar,$(TW_EXCLUDE_DEFAULT_USB_INIT)))" not in soong:
    sys.exit("BLOCKED: upstream Soong flag wiring drifted")
if len(re.findall(r'prebuilt_root\s*\{\s*name:\s*"init\.recovery\.usb\.rc"\s*,\s*src:\s*"init\.recovery\.usb\.rc"', etc)) != 1:
    sys.exit("BLOCKED: unexpected Soong USB module owner")
if not re.search(r'prebuilt_root\s*\{\s*name:\s*"init\.recovery\.usb\.rc"[\s\S]*?recovery:\s*true,\s*install_in_root:\s*true',etc):
    sys.exit("BLOCKED: Soong USB output is not recovery root")
if "TARGET_RECOVERY_FSTAB := $(DEVICE_PATH)/recovery.fstab" not in board:
    sys.exit("BLOCKED: original Songyuan fstab not selected")
if "recovery.fstab:recovery/root/system/etc/recovery.fstab" in device:
    sys.exit("BLOCKED: Make PRODUCT_COPY_FILES duplicates fstab")
if "cp -f $(item) $(TARGET_RECOVERY_ROOT_OUT)/system/etc/recovery.fstab" not in make:
    sys.exit("BLOCKED: official Makefile fstab writer missing")
if "recovery_root_private := $(strip $(wildcard $(TARGET_DEVICE_DIR)/recovery/root))" not in make:
    sys.exit("BLOCKED: TWRP recovery overlay semantics drifted")
if "$(INTERNAL_RECOVERY_RAMDISK_FILES_TIMESTAMP): $(MKBOOTFS)" not in make:
    sys.exit("BLOCKED: pre-image graph target missing")
print("PASS: one native USB Soong owner, no Make/overlay duplicate; native fstab via Makefile")
print("PENDING: graph-wide conflict proof in CI --skip-ninja phase")
