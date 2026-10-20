#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != "--staged"):
    sys.exit(2)

root = Path(sys.argv[1])
required = (
    "BoardConfig.mk", "device.mk", "twrp_songyuan.mk",
    "recovery.fstab", "twrp.flags", "prebuilt/kernel",
    "prebuilt/curated-manifest.json", "recovery/root/init.recovery.qcom.rc",
    "recovery/root/system/bin/songyuan-touch-init.sh",
    "recovery/root/system/bin/songyuan-security-setup.sh",
    "recovery/root/system/bin/songyuan-weaver-start.sh",
    "recovery/root/odm/bin/prepdecrypt.sh",
)
for name in required:
    if not (root / name).is_file():
        sys.exit("missing " + name)

board = (root / "BoardConfig.mk").read_text()
device = (root / "device.mk").read_text()
product = (root / "twrp_songyuan.mk").read_text()
fstab = (root / "recovery.fstab").read_text()
assert "PRODUCT_DEVICE := songyuan" in product
assert "PRODUCT_NAME := twrp_songyuan" in product
assert "TARGET_PREBUILT_KERNEL := $(DEVICE_PATH)/prebuilt/kernel" in board
assert "BOARD_EXCLUDE_KERNEL_FROM_RECOVERY_IMAGE := true" in board
assert "BOARD_RECOVERYIMAGE_PARTITION_SIZE := 104857600" in board
assert "TW_INCLUDE_CRYPTO_FBE := true" in board
assert "TW_INCLUDE_FBE_METADATA_DECRYPT := true" in board
assert "$(DEVICE_PATH)/twrp.flags:recovery/root/system/etc/twrp.flags" in device
assert "find-copy-subdir-files" not in device
assert "SONGYUAN_SELECTED_OEM_FILES" in device
assert "recovery/root/vendor/lib/modules/1.1" in device
assert "TW_LOAD_PREBUILT_MODULES_AT_FIRST := true" in board
for name in ("vendor", "odm", "vendor_dlkm"):
    assert f"$(DEVICE_PATH)/prebuilt/{name}" in device
assert (root / "prebuilt/kernel").stat().st_size == 42097152

mounts = set()
for line in fstab.splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    columns = line.split()
    assert len(columns) == 5, line
    assert columns[1] not in mounts, columns[1]
    mounts.add(columns[1])
assert {"/data", "/metadata", "/system", "/vendor"} <= mounts

services = {}
starts = set()
for rc in (root / "recovery/root").rglob("*.rc"):
    for line in rc.read_text().splitlines():
        stmt = line.strip().split()
        if not stmt:
            continue
        if stmt[0] == "service":
            assert len(stmt) >= 3 and stmt[1] not in services
            services[stmt[1]] = (stmt[2], rc)
        elif stmt[0] == "start":
            assert len(stmt) == 2
            starts.add(stmt[1])
assert starts <= set(services) | {"adbd"}, sorted(starts - set(services) - {"adbd"})
assert {"vendor.qseecomd", "vendor.minkdaemon", "vendor.secure_element",
        "miweaver_hal_service", "weaver_hal_service", "odm.prepdecrypt"} <= services.keys()

for service, (binpath, rc) in services.items():
    if binpath.startswith(("/vendor/", "/odm/")):
        rel = binpath.lstrip("/")
        assert (root / "recovery/root" / rel).is_file() or (root / "prebuilt" / rel).is_file(), service
assert not (root / "recovery/root/init.recovery.wifi.rc").exists()
if len(sys.argv) == 3:
    assert (root / "prebuilt/vendor/bin/qseecomd").is_file()
    assert (root / "prebuilt/odm/bin/hw/android.hardware.weaver-service.thales").is_file()
print("PASS")
