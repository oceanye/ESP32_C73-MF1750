static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_runtime_lut_hue_brightness_redpink_v3_white_containment_successor";
static constexpr const char *kCampaignId =
    "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V3_WHITE_CONTAINMENT_SUCCESSOR";
static constexpr const char *kSourceCampaignId =
    "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_V2";
static constexpr const char *kSourceMainContractId =
    "1308b6eb60ea786a2e1db2a2c984809fd446e9b1e32b1d14a54bf0356128ff8c";
static constexpr const char *kBuildTag =
    "MF1750_EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V3_WHITE_CONTAINMENT_"
    "SUCCESSOR_SINGLE_APP_BOOT_V1_2026-08-28";
static constexpr const char *kContractId =
    "1618436e99a0ee1afd9ce16e534f3cf7e34151ddb5f0d6a757aee860aff1a227";
static constexpr const char *kNvsNamespace = "rlhrpcw_v3s";
static constexpr const char *kDescriptorId =
    "8e91f5692722cc75e7ceaf32f89a330083ec39116d0e690f09387f389bd4694d";
static constexpr const char *kActionId =
    "76517f9d6ba090cef2f4f3fd32bcda6a5466b41aeeef5ce31a5520ac1dbbceed";

static constexpr const char *kPredecessorV2CampaignId =
    "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V2_WHITE_CONTAINMENT";
static constexpr const char *kPredecessorV2ContractId =
    "73f6bb1db45aa5ec570e854067cb2ad29d6994206a8816e1eadfa7fc763c2c92";
static constexpr const char *kPredecessorV2ActionId =
    "4c0c5e414242832925d864cd89b64f5592b516c70bb6669683645022b265f87b";
static constexpr const char *kPredecessorV2FirmwareBinSha256 =
    "161e7c60f03d85aa4a50d4a9f03de927acdb99f6507c696f57500d95d7aee4ce";
static constexpr const char *kPredecessorV2FirmwareElfSha256 =
    "3d759a03e42b9f6c4c2d18add6f1683432713353cb434cc3e04d506c5ccdea03";
static constexpr const char *kPredecessorV2FlashFileSha256 =
    "bfbd6799ca0bc16d81f67ee55addc137244452fb2d732364465b80e804572023";
static constexpr const char *kPredecessorV2FlashIntegritySha256 =
    "9d16ea4d96bc122aaa333b58b95ab5b5f88a87dcbcebb718ed8c716357de15eb";
static constexpr const char *kPredecessorV2DiagnosticFileSha256 =
    "67f906ce5821b3227ee5b03f74cb4ea81e96138e7eb3a333654972b768c916a7";
static constexpr const char *kPredecessorV2DiagnosticIntegritySha256 =
    "0cd81471308b9ca6dd543d451394d453622cfbe582343eef271f5b0b14ac0406";
static constexpr const char *kPredecessorV2ExpectedClassification =
    "FACTORY_OTP_WHITE_BRIGHTNESS_CAMPAIGN_CONTAINMENT_"
    "ONE_ACTION_NO_RUNTIME_PAYLOAD";
static constexpr const char *kPredecessorV2ObservedClassification =
    "FACTORY_OTP_WHITE_REDPINK_BRIGHTNESS_CONTAINMENT_"
    "ONE_ACTION_NO_RUNTIME_PAYLOAD";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V3|PROFILE=WF23_25|ROLE=BRIGHTNESS_REDPINK_OTP_WHITE_SUCCESSOR|SHA256=8e91f5692722cc75e7ceaf32f89a330083ec39116d0e690f09387f389bd4694d\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
