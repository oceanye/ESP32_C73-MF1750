static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_ENDPOINT_GALLERY_PRE_WHITE_ANCHOR_V1";
static constexpr const char *kTargetCampaignId =
    "EC5_RAW_P16_ENDPOINT_GALLERY_V1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_ENDPOINT_GALLERY_PRE_WHITE_ANCHOR_V1_2026-08-28";
static constexpr const char *kContractId =
    "c8ae63b7ab46fb2a22fc245fd8f4f2b810ea54ecf19cc71758dc3703aca2196c";
static constexpr const char *kNvsNamespace = "rp16gpw_v1";
static constexpr const char *kDescriptorId =
    "2cc71145bcd1d868c6b7d80bc25f7ac031a57dbf3ae4a234cf7e1680135144d3";
static constexpr const char *kActionId =
    "3b939eb962e43cc7c232cddb14f3d97d3d48de9c796154ff0a42eed311379a74";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_ENDPOINT_GALLERY_PRE_ANCHOR|SHA256=2cc71145bcd1d868c6b7d80bc25f7ac031a57dbf3ae4a234cf7e1680135144d3\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
