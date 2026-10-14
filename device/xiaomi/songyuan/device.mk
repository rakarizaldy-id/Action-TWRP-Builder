# Source-only Songyuan: no OEM payload and no generic/foreign vendor binaries.
$(call inherit-product, $(SRC_TARGET_DIR)/product/base.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit_only.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/virtual_ab_ota/compression_with_xor.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/emulated_storage.mk)
$(call inherit-product, vendor/twrp/config/common.mk)
BOARD_SHIPPING_API_LEVEL := 202504
PRODUCT_SHIPPING_API_LEVEL := 36
PRODUCT_TARGET_VNDK_VERSION := 36
PRODUCT_CHECK_PREBUILT_MAX_PAGE_SIZE := false
PRODUCT_USE_DYNAMIC_PARTITIONS := true
PRODUCT_PROPERTY_OVERRIDES += persist.sys.fuse.passthrough.enable=true
PRODUCT_SOONG_NAMESPACES += device/xiaomi/songyuan
TWRP_REQUIRED_MODULES += fastbootd
# DO NOT use broad PRODUCT_COPY_FILES from a generic device or private dump.
