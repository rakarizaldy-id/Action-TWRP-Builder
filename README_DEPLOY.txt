POCO F9 Ultra (songyuan) TWRP16 — public source-only candidate

Status: STATICALLY VALIDATED ONLY; build success, runtime completeness and decrypt UNPROVEN.
This ZIP is a source patch intended for the EXISTING public Action-TWRP-Builder
branch twrp16-songyuan-source-probe. It does not itself contain the 392 TWRP projects.
The existing public script scripts/songyuan-twrp16-full-source-sync.sh must remain
on that branch. GitHub Actions builds only m recovery; no stock recovery image.

HOW IT DIFFERS FROM PREVIOUS PUBLIC GENERIC SM8850:
- New target device/xiaomi/songyuan and lunch twrp_songyuan, model POCO F9 Ultra.
- Real ID305 stock fstab flags including fileencryption=ice + wrappedkey.
- Qualcomm canoe identity, stock partition layout and Android 16 SKU.
- NO inherited SM8850/Nezha prebuilts, init, vendor or kernel.
- Exports TWRP recovery ELF AND actually populated runtime files if present.
- Firmware-only and non-stock TWRP-specific files are merged/injected into a
  COPY of stock recovery.img later, IN THIS CHAT, after a path-aware diff.
- Must check dynamic linker and library closure before any boot/flash.
- FBE KeyMint -62 remains UNRESOLVED and key blob writes are forbidden.

DEPLOY: Merge contents into public repo branch; trigger ONLY new workflow:
.github/workflows/twrp16-public-songyuan-binary.yml
DO NOT trigger older sm8850 generic workflow.
