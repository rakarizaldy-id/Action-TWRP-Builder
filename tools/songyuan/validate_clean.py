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
    "usb/init.recovery.usb.rc",
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
# Owner excludes Wi-Fi even though the Ekin feature reference implements it.
# TWRP 16 checks TW_INCLUDE_WIFI; false must remain the sole assignment.
wifi_settings = [line.strip() for line in board.splitlines()
                 if line.strip().startswith("TW_INCLUDE_WIFI") and ":=" in line]
assert wifi_settings == ["TW_INCLUDE_WIFI := false"], wifi_settings
# Native Songyuan USB configfs bytes are installed ONLY by upstream
# prebuilt_root Soong, without a competing PRODUCT_COPY_FILES or overlay.
usb_selectors = [line.strip() for line in board.splitlines()
                 if line.strip().startswith("TW_EXCLUDE_DEFAULT_USB_INIT") and ":=" in line]
assert usb_selectors == ["TW_EXCLUDE_DEFAULT_USB_INIT := false"], usb_selectors
assert "    init.recovery.usb.rc \\" not in device
assert (root / "usb/init.recovery.usb.rc").is_file()
assert not (root / "recovery/root/init.recovery.usb.rc").exists()
assert "TARGET_RECOVERY_FSTAB := $(DEVICE_PATH)/recovery.fstab" in board
assert "$(DEVICE_PATH)/recovery.fstab:recovery/root/system/etc/recovery.fstab" not in device

# Inventory all native destination paths, not merely the one USB collision.
# PRODUCT_COPY_FILES has five curated native groups; duplicate targets in
# those groups would otherwise be silently ignored by Make's deduplicator.
def make_words(name):
    lines = device.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(name + " :="):
            words = []
            for current in lines[i:]:
                value = current.split(":=", 1)[1] if current == lines[i] else current
                continued = value.rstrip().endswith("\\")
                words.extend(value.rstrip().rstrip("\\").split())
                if not continued:
                    return words
            break
    raise AssertionError("Missing source-owned Make list: " + name)

native_paths = make_words("SONGYUAN_RECOVERY_FILE_PATHS")
native_paths += sum((make_words(group) for group in
                     ("SONGYUAN_NATIVE_SERVICES", "SONGYUAN_NATIVE_LIBRARIES",
                      "SONGYUAN_NATIVE_CONFIG")), [])
native_paths += ["vendor/lib/modules/1.1/" + name for name in
                 make_words("SONGYUAN_MODULE_CLOSURE")]
native_paths += ["vendor/lib/modules/1.1/modules.dep", "system/etc/recovery.fstab",
                 "system/etc/twrp.flags"]
assert len(native_paths) == len(set(native_paths)), "Duplicate native recovery install destinations"
# TWRP upstream etc/Android.bp installs these root prebuilts. All except
# USB have no same-name native destination. All must be distinct
# from native Make destinations.
twrp_root_producers = {
    "init.recovery.usb.rc", "init.recovery.ldconfig.rc",
    "init.recovery.logd.rc", "init.recovery.mksh.rc",
    "vendor_hwservice_contexts", "plat_hwservice_contexts",
    "vndservice_contexts",
}
assert not (set(native_paths) & twrp_root_producers), (
    set(native_paths) & twrp_root_producers
)
assert "$(DEVICE_PATH)/twrp.flags:recovery/root/system/etc/twrp.flags" in device
assert "find-copy-subdir-files" not in device
assert "SONGYUAN_SELECTED_OEM_FILES" in device
assert "recovery/root/vendor/lib/modules/1.1" in device
assert "TW_LOAD_PREBUILT_MODULES_AT_FIRST := true" in board
# device.mk deliberately selects OEM files through one explicit $(rel) mapping.
# A literal prebuilt/vendor or prebuilt/odm substring is NOT required in Make.
assert "$(DEVICE_PATH)/prebuilt/$(rel):recovery/root/$(rel)" in device
for group in ("SONGYUAN_NATIVE_SERVICES", "SONGYUAN_NATIVE_LIBRARIES",
              "SONGYUAN_NATIVE_CONFIG"):
    assert device.count(group + " :=") == 1, group
assert "$(DEVICE_PATH)/prebuilt/vendor_dlkm/lib/modules/$(module):recovery/root/vendor/lib/modules/1.1/$(module)" in device
assert (root / "prebuilt/kernel").stat().st_size == 42097152
assert (root / "recovery/root/odm/bin/hw/vendor.xiaomi.hardware.vibratorfeature.service").stat().st_mode & 0o111, "native vibrator HAL must be executable"

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
# Fail closed if Wi-Fi daemon, driver, script, VINTF or init is added to ramdisk.
# Native OEM archive may still contain unused WLAN modules; those are not installed.
recovery_root = root / "recovery/root"
for entry in recovery_root.rglob("*"):
    if entry.is_file():
        name = entry.name.lower()
        assert not any(term in name for term in ("wifi", "wlan", "wpa_supplicant", "cnss", "qca_cld")), entry
for name in ("TW_LOAD_VENDOR_MODULES", "SONGYUAN_MODULE_CLOSURE"):
    selection = board if name == "TW_LOAD_VENDOR_MODULES" else device
    for term in ("qca_cld", "cnss2.ko", "cfg80211.ko", "wlan_firmware_service"):
        assert term not in selection, (name, term)
if len(sys.argv) == 3:
    assert (root / "prebuilt/vendor/bin/qseecomd").is_file()
    assert (root / "prebuilt/odm/bin/hw/android.hardware.weaver-service.thales").is_file()
print("PASS")
