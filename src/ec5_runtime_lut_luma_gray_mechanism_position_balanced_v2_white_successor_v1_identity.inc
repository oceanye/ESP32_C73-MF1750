#pragma once

static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId = "ec5_luma_gray_mpb_v2_white_v1";
static constexpr const char *kCampaignId =
    "EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_FACTORY_OTP_WHITE_SUCCESSOR_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2";
static constexpr const char *kSourceMainContractId =
    "b9baafc7b0e4966a23eb1189372e36d690e8df84d8e17f4c8cbc3536be46f019";
static constexpr const char *kBuildTag =
    "MF1750_EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_FACTORY_OTP_WHITE_SUCCESSOR_V1_2026-09-01";
static constexpr const char *kContractId =
    "330a2e8a685ab399a032233e3a976dd1147e86ce2552574bc8a3a47e0f7fa495";
static constexpr const char *kNvsNamespace = "lgmpb2w_v1";
static constexpr const char *kDescriptorId =
    "d51e6302c5336cee29e50be52b344e60334d243ee5e2fbd9bcfdcb82d650ccf5";
static constexpr const char *kActionId =
    "e7127fe1c2c3e871578bc17f50c17f4db4d6161e54df0c94c2820d0ba20e71e3";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_AFTER_LGMPB2_G3_OR_G4_COMPLETE|SHA256=d51e6302c5336cee29e50be52b344e60334d243ee5e2fbd9bcfdcb82d650ccf5\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
