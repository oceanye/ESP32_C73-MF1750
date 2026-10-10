static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_same_r20_aa_abort_white_v1";
static constexpr const char *kCampaignId = "EC5_SAME_R20_AA_ABORT_WHITE_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_SAME_R20_PARITY_2X4_V1";
static constexpr const char *kSourceContractId =
    "718d6cf628cd14a869b73f77f6414fcdd8a5b364863849899403afde2f3463f8";
static constexpr const char *kSourceFirmwareBinSha256 =
    "d65fb20b3e3843563561340d6bb450fc469ade4e503fec87eec3f0369e30977f";
static constexpr const char *kSourceFirmwareElfSha256 =
    "bf15d35d12af897d89afd2ab65141a50dd3dc4e2350877abc3ada530f8de94b6";
static constexpr const char *kSourceActionId =
    "7dd101c61553c9a10b97beeb7c3c8ce26e79c410d3b2ac3040db572065fd49f4";
static constexpr const char *kSourceActionFileSha256 =
    "80a6e7172967e15a87756a2d9c3478a821b357ed2d8d39845e9d5bf15dfef751";
static constexpr const char *kSourceRepeatReportSha256 =
    "172f3570e33701c9cf10a8d9f3c4fbb4c146e8fa8ee26d6f5a3e2f369809b67d";
static constexpr const char *kSourceRepeatReportId =
    "60b1c65ec69a28ab44b6c32547db2975199e2a74237463e86018abae494e91c1";
static constexpr const char *kSourceCameraFileSetSha256 =
    "1860de17ba79bf9c1a5f4a48cd23d5559ee66f26ecc4f5d357f1790700fe6efb";
static constexpr const char *kSourceRelayOffReceiptSha256 =
    "c523566cf21a518108e27f47ceb7a030d3e19205a0abab0fa283f36461568c35";
static constexpr const char *kBuildTag =
    "MF1750_EC5_SAME_R20_AA_ABORT_WHITE_V1_SINGLE_APP_BOOT_2026-08-28";
static constexpr const char *kContractId =
    "08e2683209d66e5f4a4149733e0b446abc81be29b2ed6cec1637ddafd66f0399";
static constexpr const char *kNvsNamespace = "sr20aaw_v1";
static constexpr const char *kDescriptorId =
    "65e534e7632bab1320b2d40f531bb00c55bdfaaf56441e52b1920837ba12d66c";
static constexpr const char *kActionId =
    "902629decf24660f7cbb7495336f8f15b250097398aa4965d1c3b1d4ec79b268";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=SAME_R20_AA_ABORT_OTP_WHITE|SHA256=65e534e7632bab1320b2d40f531bb00c55bdfaaf56441e52b1920837ba12d66c\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
