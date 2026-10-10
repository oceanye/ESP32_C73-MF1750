static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_raw_p16_endpoint_gallery_v1_white_containment";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_RAW_P16_ENDPOINT_GALLERY_V1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_V1_2026-08-28";
static constexpr const char *kContractId =
    "1d08798ba1a4012623c64625cec2edfaeb160aa3b20f0a2a98406994b55cce14";
static constexpr const char *kNvsNamespace = "rp16gw_v1";
static constexpr const char *kDescriptorId =
    "03920a12ad8f0b96e2dc6ae8281fa07da3cfb8ccc84da86dfb3f2cf2334f84dc";
static constexpr const char *kActionId =
    "12a146d8ad678165e1061fda3e7569743e28d663ee349b46ee900196b95d8cd6";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_ENDPOINT_GALLERY_CONTAINMENT|SHA256=03920a12ad8f0b96e2dc6ae8281fa07da3cfb8ccc84da86dfb3f2cf2334f84dc\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
