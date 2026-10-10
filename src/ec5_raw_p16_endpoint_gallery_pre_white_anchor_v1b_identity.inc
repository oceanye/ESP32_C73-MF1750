static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1b";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_ENDPOINT_GALLERY_PRE_WHITE_ANCHOR_V1B";
static constexpr const char *kTargetCampaignId =
    "EC5_RAW_P16_ENDPOINT_GALLERY_V1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_ENDPOINT_GALLERY_PRE_WHITE_ANCHOR_V1B_2026-08-28";
static constexpr const char *kContractId =
    "d6c88b8df003f42fe9415682d412e4d5cd1c15ceb2ee7423c927a603d0332c61";
static constexpr const char *kNvsNamespace = "rp16gpw_v1b";
static constexpr const char *kDescriptorId =
    "ba9442de357eb7c14da7ded2e171f2ceacca0b2fdd00575500a78ebeadb28dd3";
static constexpr const char *kActionId =
    "e66d01310335accc78c0ce00d05bfe0bb2e1842b5826ab221d10207c38de740e";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_ENDPOINT_GALLERY_PRE_ANCHOR_SUCCESSOR_V1B|SHA256=ba9442de357eb7c14da7ded2e171f2ceacca0b2fdd00575500a78ebeadb28dd3\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
