#!/usr/bin/env python3
"""Ensure public Songyuan build inputs are genuinely Songyuan and source-only."""
from pathlib import Path
import sys
p=Path(sys.argv[1])
def f(s):
    d=p/s
    if not d.is_file() or not d.stat().st_size:
        raise SystemExit(f"Missing {d}")
    return d.read_text()
board=f('BoardConfig.mk');prod=f('twrp_songyuan.mk');fstab=f('recovery.fstab');dev=f('device.mk')
for needle in ('PRODUCT_NAME := twrp_songyuan','PRODUCT_DEVICE := songyuan','PRODUCT_BRAND := POCO','PRODUCT_MODEL := POCO F9 Ultra'):
    assert needle in prod,needle
for needle in ('PRODUCT_PLATFORM := canoe','BOARD_RECOVERYIMAGE_PARTITION_SIZE := 104857600','TARGET_NO_KERNEL := true','TW_INCLUDE_FBE_METADATA_DECRYPT := true'):
    assert needle in board,needle
for needle in ('fileencryption=ice,wrappedkey,keydirectory=/metadata/vold/metadata_encryption','wrappedkey,first_stage_mount','/mnt/vendor/mi_ext','avb=vbmeta_system'):
    assert needle in fstab,needle
assert 'PRODUCT_COPY_FILES' not in '\n'.join(x for x in dev.splitlines() if not x.lstrip().startswith('#'))
for d in ('prebuilt','recovery/root/vendor','recovery/root/odm','recovery/root/vendor_dlkm'):
    assert not (p/d).exists(),f'Forbidden OEM/foreign binary tree: {d}'
assert not list(p.rglob('*.ko')) and not list(p.rglob('*.img'))

# Regression gates informed by the COMPLETE public run #38568569017 logs.
# Android build/make/core/board_config.mk refuses recovery-image-only settings
# when BUILDING_RECOVERY_IMAGE is absent; this target builds only an ELF.
import re
for variable in ('BOARD_EXCLUDE_KERNEL_FROM_RECOVERY_IMAGE',
                 'BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT',
                 'BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT',
                 'BOARD_VENDOR_RAMDISK_FRAGMENTS'):
    if re.search(r'^\\s*' + re.escape(variable) + r'\\s*(?:[:+?]?=)', board, re.M):
        raise SystemExit(f'FAIL ELF-only: image-specific BoardConfig variable {variable}')
assert 'TARGET_PREBUILT_KERNEL' not in board, 'Public target must not reference absent private kernel'
assert 'TARGET_PREBUILT_DTB' not in board, 'Public target must not reference absent private dtb'
assert '$(LOCAL_DIR)/twrp_songyuan.mk' in f('AndroidProducts.mk')
assert '$(call inherit-product, vendor/twrp/config/common.mk)' in dev
assert 'twrp_sm8850' not in prod, 'Generic target alias forbidden'
assert 'TARGET_RECOVERY_FSTAB := $(DEVICE_PATH)/recovery.fstab' in board
for name in ('TW_INCLUDE_CRYPTO := true', 'TW_INCLUDE_CRYPTO_FBE := true',
             'TW_CRYPTO_USE_VENDOR_KEYMINT := true', 'TW_INCLUDE_OMAPI := true'):
    assert name in board, 'Expected TWRP16 feature absent: ' + name
assert 'ro.product.device=songyuan' in f('system.prop')
for file in p.rglob('*'):
    if file.is_file():
        assert not file.is_symlink(), f'Symlink forbidden in public tree: {file}'
        assert file.suffix.lower() not in ('.bin','.so','.mbn','.dtb','.dtbo','.elf'), f'OEM/binary file forbidden: {file}'

print('PASS public Songyuan native source-only tree; NO OEM binaries, NO generic lunch target')
