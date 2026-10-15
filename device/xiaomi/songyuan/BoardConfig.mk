# POCO F9 Ultra (songyuan) TWRP16 source-only target; firmware ID305.
# Device identifiers, partition layout and encryption flags audited from stock.
# No proprietary kernel, trustlets, vendor/odm blobs or private device files.
DEVICE_PATH := device/xiaomi/songyuan
ALLOW_MISSING_DEPENDENCIES := true
BUILD_BROKEN_DUP_RULES := true
BUILD_BROKEN_ELF_PREBUILT_PRODUCT_COPY_FILES := true
TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-a
TARGET_CPU_ABI := arm64-v8a
TARGET_CPU_ABI2 :=
TARGET_CPU_VARIANT := generic
PRODUCT_PLATFORM := canoe
TARGET_BOOTLOADER_BOARD_NAME := $(PRODUCT_PLATFORM)
TARGET_NO_BOOTLOADER := true
# Build-system platform alias inherited from the working YuKongA source; NOT
# the lunch target, NOT a foreign device's prebuilt firmware.
TARGET_BOARD_PLATFORM := xiaomi_sm8850
TARGET_BOARD_PLATFORM_GPU := qcom-adreno840
QCOM_BOARD_PLATFORMS += xiaomi_sm8850
# Public CI builds ONLY `m recovery` ELF, never a full boot/recovery image.
# Clean ID305 kernel is deliberately private and used only in chat integration.
TARGET_NO_KERNEL := true
BOARD_BOOT_HEADER_VERSION := 4
BOARD_KERNEL_PAGESIZE := 4096
BOARD_RAMDISK_USE_LZ4 := true
# Only m recovery ELF is built, not an image. Do not define the image-only BOARD_EXCLUDE_KERNEL_FROM_RECOVERY_IMAGE.
AB_OTA_UPDATER := true
BOARD_AVB_ENABLE := true
BOARD_PROPERTY_OVERRIDES_SPLIT_ENABLED := true
TARGET_COPY_OUT_VENDOR := vendor
TARGET_COPY_OUT_ODM := odm
TARGET_COPY_OUT_VENDOR_DLKM := vendor_dlkm
BOARD_USES_VENDOR_DLKMIMAGE := true
BOARD_VENDOR_DLKMIMAGE_FILE_SYSTEM_TYPE := ext4
BOARD_ODMIMAGE_FILE_SYSTEM_TYPE := ext4
BOARD_RECOVERYIMAGE_PARTITION_SIZE := 104857600
BOARD_SUPER_PARTITION_SIZE := 14495514624
BOARD_SUPER_PARTITION_GROUPS := qti_dynamic_partitions
BOARD_QTI_DYNAMIC_PARTITIONS_SIZE := $(shell echo $$(($(BOARD_SUPER_PARTITION_SIZE) - 10485760)))
BOARD_QTI_DYNAMIC_PARTITIONS_PARTITION_LIST := system system_ext product vendor vendor_dlkm odm system_dlkm
BOARD_ROOT_EXTRA_FOLDERS := bluetooth dsp firmware persist soccp
TARGET_USERIMAGES_USE_EXT4 := true
TARGET_USERIMAGES_USE_F2FS := true
TARGET_SYSTEM_PROP += $(DEVICE_PATH)/system.prop
TARGET_RECOVERY_PIXEL_FORMAT := RGBX_8888
TARGET_RECOVERY_FSTAB := $(DEVICE_PATH)/recovery.fstab
TW_INCLUDE_CRYPTO := true
TW_INCLUDE_CRYPTO_FBE := true
TW_INCLUDE_FBE_METADATA_DECRYPT := true
BOARD_USES_METADATA_PARTITION := true
TW_INCLUDE_OMAPI := true
TW_USE_FSCRYPT_POLICY := 2
TW_CRYPTO_USE_VENDOR_KEYMINT := true
# Existing TWRP compatibility identity; differs from stock ID305 patch date.
# This is NOT proof of FBE decrypt and MUST NOT write upgraded key blobs.
PLATFORM_VERSION := 99.87.36
PLATFORM_VERSION_LAST_STABLE := $(PLATFORM_VERSION)
PLATFORM_SECURITY_PATCH := 2099-12-31
VENDOR_SECURITY_PATCH := $(PLATFORM_SECURITY_PATCH)
BOOT_SECURITY_PATCH := $(PLATFORM_SECURITY_PATCH)
TW_INCLUDE_7ZA := true
TW_INCLUDE_ZSTD := true
TW_INCLUDE_REPACKTOOLS := true
TW_INCLUDE_RESETPROP := true
TW_INCLUDE_LIBRESETPROP := true
TW_ENABLE_ALL_PARTITION_TOOLS := true
TARGET_USES_LOGD := true
TWRP_INCLUDE_LOGCAT := true
TW_INCLUDE_FASTBOOTD := true
TW_THEME := portrait_hdpi
TW_FRAMERATE := 120
RECOVERY_SDCARD_ON_DATA := true
TARGET_RECOVERY_QCOM_RTC_FIX := true
TW_EXCLUDE_DEFAULT_USB_INIT := true
TW_INCLUDE_NTFS_3G := true
TW_USE_DMCTL := true
TW_USE_TOOLBOX := true
TARGET_USES_MKE2FS := true
TW_INPUT_BLACKLIST := "hbtp_vm:uinput-xiaomi"
TW_BRIGHTNESS_PATH := "/sys/class/backlight/panel0-backlight/brightness"
TW_MAX_BRIGHTNESS := 16383
TW_DEFAULT_BRIGHTNESS := 950
TW_EXTRA_LANGUAGES := true
TW_EXCLUDE_APEX := true
TW_STATUS_ICONS_ALIGN := bottom
TW_SUPPORT_INPUT_AIDL_HAPTICS := true
TW_SUPPORT_INPUT_AIDL_HAPTICS_FIX_OFF := true
TW_USE_SERIALNO_PROPERTY_FOR_DEVICE_ID := true
TW_CUSTOM_CPU_TEMP_PATH := "/sys/class/thermal/thermal_zone75/temp"
# Stock kernel module names and secure HAL binaries remain in PRIVATE data.
# Runtime injection into stock carrier is deferred to THIS CHAT.

# STAGE8 REVIEW BRANCH ONLY: the successful source-only ELF compile omitted
# TW_LOAD_VENDOR_MODULES; in TWRP-Test twrp-16.0 this excludes the module loader.
# These 69 requested module filenames are copied from verified private Songyuan
# BoardConfig, each present in the 73-module ID305 OEM inventory. No OEM binaries
# are part of this PUBLIC repository or its build outputs.
# Do NOT merge/boot this alone: upstream kernel_module_loader.cpp sets
# twrp.modules.loaded=true after an attempt even if modules failed to load.
# Keep Songyuan hardware/security RC gated by a separate observed-ready property.
TW_LOAD_VENDOR_MODULES := "qmi_helpers.ko qcom_glink.ko qcom_glink_smem.ko qcom_smd.ko rproc_qcom_common.ko qcom_pdr_msg.ko pdr_interface.ko qcom_sysmon.ko qcom_q6v5.ko qcom_ramdump.ko qcom_va_minidump.ko qcom_pil_info.ko qcom_q6v5_pas.ko q6_pdr_dlkm.ko q6_notifier_dlkm.ko snd_event_dlkm.ko gpr_dlkm.ko spf_core_dlkm.ko adsp_loader_dlkm.ko q6_dlkm.ko pcie-pdc.ko pci-msm-drv.ko mhi.ko wcd_usbss_i2c.ko usb_f_gsi.ko dwc3-msm.ko repeater.ko redriver.ko ipam.ko gsim.ko rmnet_mem.ko smem-mailbox.ko cfg80211.ko mac80211.ko wlan_firmware_service.ko cnss_prealloc.ko cnss_utils.ko cnss_nl.ko cnss_plat_ipc_qmi_svc.ko cnss2.ko qca_cld3_peach_v2.ko qca_cld3_wcn7750.ko qti_pmic_glink.ko qti_battery_charger.ko panel_event_notifier.ko gh_irq_lend.ko xiaomi_touch.ko focaltech_touch_3685g_1.ko swr_dlkm.ko mca_sysfs.ko mca_event.ko mca_log.ko mca_parse_dts.ko mca_charge_mievent.ko mca_protocol_class.ko mca_protocol_qc_class.ko mca_platform_bc12_class.ko mca_platform_buckchg_class.ko mca_strategy_class.ko mca_adsp_glink.ko mca_qcom_subpmic_proxy.ko leds-qcom-flash.ko leds-qpnp-vibrator-ldo.ko qcom-hv-haptics.ko swr_haptics_dlkm.ko smcinvoke_dlkm.ko qsee_ipc_irq_bridge.ko stm_st54se_gpio.ko stm_nfc_i2c.ko"
TW_LOAD_VENDOR_MODULES_EXCLUDE_GKI := true
