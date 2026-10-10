static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_runtime_lut_luma_gray_v1_white_containment";
static constexpr const char *kCampaignId =
    "EC5_LUMA_GRAY_V1_FACTORY_OTP_WHITE_CONTAINMENT";
static constexpr const char *kSourceCampaignId =
    "EC5_LUMA_GRAY_EXPLORATORY_2PAGE_V1";
static constexpr const char *kSourceMainContractId =
    "db671c68cc1141231cbb0baf5f0667e6cdc292095af7b4f3cf9c3d5001d1b260";
static constexpr const char *kBuildTag =
    "MF1750_EC5_LUMA_GRAY_V1_FACTORY_OTP_WHITE_CONTAINMENT_2026-08-28";
static constexpr const char *kContractId =
    "d75573f6413dd861411147047c3784e0560de44241017eafc3cf46c274b99736";
static constexpr const char *kNvsNamespace = "rllgw_v1";
static constexpr const char *kDescriptorId =
    "4cd35729e2d512bcac1f476019149784e312d2ce19c52cf30e156407c91e6b3f";
static constexpr const char *kActionId =
    "4622f4035bfc9d8cab7b260e7911e9a70b86529eeeb0a4c23ad86a30ba63794d";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V2|PROFILE=WF23_25|ROLE=LUMA_GRAY_V1_OTP_WHITE_CONTAINMENT|SHA256=4cd35729e2d512bcac1f476019149784e312d2ce19c52cf30e156407c91e6b3f\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
