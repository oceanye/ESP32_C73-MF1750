#if !defined(MF1750_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2_WHITE_BUILD)
#error "W4 T3 AC profile-following successor V2 white identity requires its isolated selector"
#endif

static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_raw_p16_crossover_w4_after_t3_ac_profile_following_successor_v2_white_v1";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2_WHITE_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2";
static constexpr const char *kSourceContractId =
    "cc33b55a64fc2d54884f9c6ca65e117d6767fab0f0c60c3e5f55fac3554e5729";
static constexpr const char *kSourceDescriptorId =
    "c2e40c4c59cf6cca3f6ff4fd8c568a5ddee59e8c2100a9cf5d50c007317a148a";
static constexpr const char *kSourceActionId =
    "73f6e97b49b5bd8c46edbba9edffde99967dcb170be6150082dc7c68100fada5";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2_WHITE_V1_2026-08-31";
static constexpr const char *kContractId =
    "a75af9d7fcfc425ffff18f08d2c6f59eec61b1a4e8e53a3c18bcf2783767e6bb";
static constexpr const char *kNvsNamespace = "p16w4pf2_v1";
static constexpr const char *kFreshWhiteNvsKey = "used_w4pf21";
static constexpr const char *kDescriptorId =
    "45e796933c4006b6b7afa050e2a4ba25fd9d78a922bf00ba11f0193002909e04";
static constexpr const char *kActionId =
    "7d600b1a0072a1966e5240dec8756094962066d2ebd3fff555af2d93da3407f4";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2|SHA256=45e796933c4006b6b7afa050e2a4ba25fd9d78a922bf00ba11f0193002909e04\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
