#!/usr/bin/env python3
"""Run negative mutation tests before expensive 392-project source sync."""
from pathlib import Path
import shutil, subprocess, sys, tempfile

src=Path(sys.argv[1] if len(sys.argv)>1 else "device/xiaomi/songyuan").resolve()
checker=Path(__file__).with_name("validate-songyuan-source-only.py")
def verify(path,should_pass,label):
    p=subprocess.run([sys.executable,str(checker),str(path)],capture_output=True,text=True)
    good=p.returncode==0
    if good!=should_pass:
        raise SystemExit(f"FAIL regression {label}: rc={p.returncode}\n{p.stdout}\n{p.stderr}")
    print("PASS regression:",label)

verify(src,True,"original real Songyuan source-only target")
with tempfile.TemporaryDirectory(prefix="songyuan-regression-") as tmp:
    cases=[
        ("image-only flag","BoardConfig.mk","\nBOARD_EXCLUDE_KERNEL_FROM_RECOVERY_IMAGE := true\n"),
        ("vendor-boot image flag","BoardConfig.mk","\nBOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT := true\n"),
        ("wrong generic target","twrp_songyuan.mk","\nPRODUCT_NAME := twrp_sm8850\n"),
        ("unfiltered proprietary copy","device.mk","\nPRODUCT_COPY_FILES += $(DEVICE_PATH)/recovery/root/vendor/lib64/private.so:recovery/root/vendor/lib64/private.so\n"),
    ]
    for number,(label,file,addition) in enumerate(cases):
        dst=Path(tmp)/str(number)
        shutil.copytree(src,dst)
        with (dst/file).open("a") as f: f.write(addition)
        verify(dst,False,label)
    wrong=Path(tmp)/"bad_fbe"
    shutil.copytree(src,wrong)
    p=wrong/"recovery.fstab"
    text=p.read_text()
    token="fileencryption=ice,wrappedkey,keydirectory=/metadata/vold/metadata_encryption"
    if token not in text: raise SystemExit("FAIL regression input missing OEM cipher")
    p.write_text(text.replace(token,"fileencryption=none"))
    verify(wrong,False,"wrong stock ID305 FBE")
print("PASS all pre-sync source-only regression tests")
