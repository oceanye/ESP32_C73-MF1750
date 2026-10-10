#pragma once

// Frozen, compile-visible authority for the independent post-L3/L4 factory
// OTP white action.  The descriptor transitively binds both accepted source
// actions and the exact sealed Latin-V3 application artifacts.
static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_stable_c0_luma_lat_v3_white_v1";
static constexpr const char *kCampaignId =
    "EC5_STABLE_CODE0_LUMA_LATIN_V3_FACTORY_OTP_WHITE_SUCCESSOR_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_STABLE_CODE0_LUMA_LATIN_V3";
static constexpr const char *kSourceMainContractId =
    "472cb28efa39538963cc94da3d8442f2a0e35603fdd41f38eb973bcb600f8302";
static constexpr const char *kBuildTag =
    "MF1750_EC5_STABLE_CODE0_LUMA_LATIN_V3_FACTORY_OTP_WHITE_SUCCESSOR_V1_2026-09-01";
static constexpr const char *kContractId =
    "787c2898a841913ac009e0284a1f3680403cc77a05ec700cb17f1a4a08152377";
static constexpr const char *kNvsNamespace = "scl3w_v1";
static constexpr const char *kDescriptorId =
    "8e74da212546b89bfdeba9e6638b30a8d4aa75114d394387c3d2a3b73f8276e0";
static constexpr const char *kActionId =
    "7d68be7197e6af89e6a7d500010160b6c11343ae5f92d990e1b982275fb5245f";
static constexpr const char *kAcceptedSourceActionsSha256 =
    "e72a128241a5e3ed73e4cd2c86eb8636799552087af924cd1aa3a30a2ab25da7";
static constexpr const char *kSourceFirmwareBinSha256 =
    "16f63947918d244e27edd0a7f3d0c3f4ff895fa02cbc26c31461c9d91ea7b737";
static constexpr const char *kSourceFirmwareElfSha256 =
    "c3e763105daeec2bc610daef2aad7e4b8c138d3c95cf414fa343aa067adcdcdb";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_AFTER_STABLE_CODE0_LATIN_V3_L3_OR_L4_COMPLETE|SHA256=8e74da212546b89bfdeba9e6638b30a8d4aa75114d394387c3d2a3b73f8276e0\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
