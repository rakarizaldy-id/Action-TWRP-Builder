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
print('PASS public Songyuan native source-only tree; NO OEM binaries, NO generic lunch target')
