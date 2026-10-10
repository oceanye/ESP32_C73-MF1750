#pragma once

static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId = "ec5_luma_gray_mpb_v3_white_v1";
static constexpr const char *kCampaignId =
    "EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3_FACTORY_OTP_WHITE_SUCCESSOR_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3";
static constexpr const char *kSourceMainContractId =
    "a114a46bec02b5de80c1f63757723e90cf8e101a81429a8f47eabadc471e3b88";
static constexpr const char *kBuildTag =
    "MF1750_EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3_FACTORY_OTP_WHITE_SUCCESSOR_V1_2026-09-01";
static constexpr const char *kContractId =
    "19990cdb72503ad98c282d6c5358ba5b0ddd7c9d354f1fc16d7079efd611070d";
static constexpr const char *kNvsNamespace = "lgmpb3w_v1";
static constexpr const char *kDescriptorId =
    "0e19ef777b8fa3c510e04dd176e79d09461d1b4f7bc27d7d528563b121aee88e";
static constexpr const char *kActionId =
    "87d2751ff18118474f9cc1a8629e384866dbc708de8f698eb1dac927a7fbc3be";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_AFTER_LGMPB3_G3_OR_G4_COMPLETE|SHA256=0e19ef777b8fa3c510e04dd176e79d09461d1b4f7bc27d7d528563b121aee88e\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
