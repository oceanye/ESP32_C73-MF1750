#pragma once

// Frozen compile-visible authority. H2 COMPLETE is the default source; H1 is
// accepted only when the host selects the explicit-H1-stop branch.
static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_position_balanced_gray_hold_successor_v1_white_v1";
static constexpr const char *kCampaignId =
    "EC5_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1_FACTORY_OTP_WHITE_SUCCESSOR_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1";
static constexpr const char *kSourceMainContractId =
    "329e0bb6075291cc2bbdc1045a642b055b06fb8d312d2a7761b1332358e04229";
static constexpr const char *kBuildTag =
    "MF1750_EC5_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1_FACTORY_OTP_WHITE_SUCCESSOR_V1_2026-09-01";
static constexpr const char *kContractId =
    "79ac7bae08b912cdcbf3d959029d56c740407275ef70c91de738b8205dcaa433";
static constexpr const char *kNvsNamespace = "pbghsw_v1";
static constexpr const char *kDescriptorId =
    "c8492ebc83abd0a1721abfd4ae001f405bb21e0e1d87ae1ae20fb076f6be41c6";
static constexpr const char *kActionId =
    "934330c22eb1057c7595c5db6711bfcbc7647291e56f5bd8acd059aa6a65e21d";
static constexpr const char *kAcceptedSourceActionsSha256 =
    "4d5659c29c6c64e305fbe275bd69892b3f0bfb1d7be7ea58583bd8c2255896e6";
static constexpr const char *kSourceFirmwareBinSha256 =
    "5a0d80b7391ae8f171747a1505521ff7193757bef86bf5e34bfb1f5be2d95db8";
static constexpr const char *kSourceFirmwareElfSha256 =
    "c7c5f1467afef0d496327ea2b086daf6a455e5de174e071f34b4f4d7ee6fecf1";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_AFTER_PBGHS1_H2_DEFAULT_OR_EXPLICIT_H1_STOP|SHA256=c8492ebc83abd0a1721abfd4ae001f405bb21e0e1d87ae1ae20fb076f6be41c6\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
