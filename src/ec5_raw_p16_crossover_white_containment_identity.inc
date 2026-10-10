#if (defined(MF1750_RAW_P16_CROSSOVER_WHITE_W1_BUILD) + \
     defined(MF1750_RAW_P16_CROSSOVER_WHITE_W2_BUILD) + \
     defined(MF1750_RAW_P16_CROSSOVER_WHITE_W3_BUILD)) != 1
#error "RAW-P16 crossover white containment must select one fresh campaign"
#endif

static constexpr const char *kProfileId = "WF23_25";

#if defined(MF1750_RAW_P16_CROSSOVER_WHITE_W1_BUILD)
static constexpr const char *kEnvironmentId =
    "ec5_raw_p16_crossover_w1_after_t1_white_v1";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_CROSSOVER_W1_AFTER_T1_WHITE_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_RAW_P16_CROSSOVER_POSBAL_T1_AC_V1";
static constexpr const char *kSourceContractId =
    "6ea93bbd9be1d75e12bc6656614ac335faeb97aa1079ff04733b8babe7a247d7";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_CROSSOVER_W1_AFTER_T1_WHITE_V1_2026-08-30";
static constexpr const char *kContractId =
    "7c6afcd9dd4bfd26d52659d22687bdfe3bf8b891ed86cd0783538a720ddddd70";
static constexpr const char *kNvsNamespace = "p16x_w1_v1";
static constexpr const char *kFreshWhiteNvsKey = "used_w1";
static constexpr const char *kDescriptorId =
    "c5314b8fede1a88e8e468d142856c6c2d79252a8acbd242749808161f50e1bbb";
static constexpr const char *kActionId =
    "f8cf26e3c344d78ddebd06a570ad19f7cad879cf8b5d6d3f9ce620e86bd850a5";
#elif defined(MF1750_RAW_P16_CROSSOVER_WHITE_W2_BUILD)
static constexpr const char *kEnvironmentId =
    "ec5_raw_p16_crossover_w2_after_t2_white_v1";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_CROSSOVER_W2_AFTER_T2_WHITE_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_RAW_P16_CROSSOVER_POSBAL_T2_CA_V1";
static constexpr const char *kSourceContractId =
    "ddcde0da8f5fec1b73924131a9a3e92fbee632430a041a72c56eea8a32b9d3cf";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_CROSSOVER_W2_AFTER_T2_WHITE_V1_2026-08-30";
static constexpr const char *kContractId =
    "2888c7cdcb0ff22850ecfa25efcd722646cc21b68f4da43347d9af98a94a8615";
static constexpr const char *kNvsNamespace = "p16x_w2_v1";
static constexpr const char *kFreshWhiteNvsKey = "used_w2";
static constexpr const char *kDescriptorId =
    "aa326121718e574ff02bf373e80ca7ac3bfc2caef4aa05259be14f9a049884c2";
static constexpr const char *kActionId =
    "b0c81939e444c2e9d062e9d54850604409d89e81d59b521f28f8f46c1d456a4f";
#else
static constexpr const char *kEnvironmentId =
    "ec5_raw_p16_crossover_w3_final_after_t3_white_v1";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_CROSSOVER_W3_FINAL_AFTER_T3_WHITE_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_RAW_P16_CROSSOVER_POSBAL_T3_AC_REPEAT_V1";
static constexpr const char *kSourceContractId =
    "60f27623af8527f240173e457060ba008e61083f985e2b4a6ad4914a1f3705a0";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_CROSSOVER_W3_FINAL_AFTER_T3_WHITE_V1_2026-08-30";
static constexpr const char *kContractId =
    "b7e984233f33c826f7882e44ede6297f38b5308947c02cd7561f2883e247ee6c";
static constexpr const char *kNvsNamespace = "p16x_w3_v1";
static constexpr const char *kFreshWhiteNvsKey = "used_w3";
static constexpr const char *kDescriptorId =
    "0d04b8ba84fa729a7a525bd598a94a42b713be0518c832e670fda4b6e90da462";
static constexpr const char *kActionId =
    "c8e00dcb3a5d3bff11c192b56d7fc3074605be561fec1fb5688a065444365c63";
#endif

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
#if defined(MF1750_RAW_P16_CROSSOVER_WHITE_W1_BUILD)
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W1|SHA256=c5314b8fede1a88e8e468d142856c6c2d79252a8acbd242749808161f50e1bbb\"\n"
#elif defined(MF1750_RAW_P16_CROSSOVER_WHITE_W2_BUILD)
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W2|SHA256=aa326121718e574ff02bf373e80ca7ac3bfc2caef4aa05259be14f9a049884c2\"\n"
#else
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W3|SHA256=0d04b8ba84fa729a7a525bd598a94a42b713be0518c832e670fda4b6e90da462\"\n"
#endif
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
