#if MF1750_LEGACY_REFERENCE_MATRIX == 1
#include "ec5_reference_field_candidate.inc"
#else
#include "ec5_pure_field_candidate.inc"
#endif

static constexpr const char *kProfileId = PF_EXPECTED_PROFILE;
static constexpr const char *kEnvironmentId =
    "ec5_pfm_" PF_NAME_LOWER "_white";
static constexpr const char *kCampaignId =
#if MF1750_LEGACY_REFERENCE_MATRIX == 1
    "MF1750_STAGE3_REFERENCE_535_MATRIX_20260822";
#else
    "MF1750_STAGE3_PURE_FIELD_MATRIX_20260822";
#endif
static constexpr const char *kBuildTag =
    "MF1750_EC5_PURE_FIELD_" PF_NAME "_WHITE_V1_2026-08-22";
static constexpr const char *kContractId = PF_CONTRACT;
static constexpr const char *kNvsNamespace = "pfw" PF_NAME_LOWER;
static constexpr const char *kDescriptorId = PF_WHITE_DESCRIPTOR;
static constexpr const char *kActionId = PF_WHITE_ACTION;

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=" PF_EXPECTED_PROFILE
    "|ROLE=OTP_WHITE|SHA256=" PF_WHITE_DESCRIPTOR "\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
