static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_rlph_v3_containment_white";
static constexpr const char *kCampaignId =
    "EC5_RUNTIME_LUT_PARTIAL_HOLD_V3_CONTAINMENT_20260823";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_V3_CONTAINMENT_WHITE_V1_2026-08-23";
static constexpr const char *kContractId =
    "57257364eb00c4cd15faa294c456e6e87e3b8ba7368bf70a72fead1e28bf43ab";
static constexpr const char *kNvsNamespace = "rlphv3cw";
static constexpr const char *kDescriptorId =
    "1b85ec877e780f45b30aa69f127472cc22535474b03a5fb7d0d19e87e5ca67d3";
static constexpr const char *kActionId =
    "c24baf700cf8ce45eedcdcde252728ef4d4fd016c3ceaa1dbef7d76699cfab02";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE|SHA256=1b85ec877e780f45b30aa69f127472cc22535474b03a5fb7d0d19e87e5ca67d3\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
