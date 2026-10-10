#if !defined(MF1750_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_WHITE_BUILD)
#error "W4 T3 AC profile-following successor white identity requires its isolated selector"
#endif

static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_raw_p16_crossover_w4_after_t3_ac_profile_following_successor_white_v1";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_WHITE_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V1";
static constexpr const char *kSourceContractId =
    "714ddf2e44725361e9b404ce512d9c9a96a96d7b31cce8bfbd4555d0883e9e19";
static constexpr const char *kSourceDescriptorId =
    "52de5c169b19bf7db2788f73e2c450971bb6adffb7c305cb0dd8d7873b9b3af9";
static constexpr const char *kSourceActionId =
    "db009936f341cd612be9aa47d08a0a316ec2c581c3c88d35d089ce3fa5857104";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_WHITE_V1_2026-08-30";
static constexpr const char *kContractId =
    "7edf2e1916d536aa8b7d6d77be19899aab4fc6816e8c48de1e1b621bff0b7d52";
static constexpr const char *kNvsNamespace = "p16w4pf_v1";
static constexpr const char *kFreshWhiteNvsKey = "used_w4pf1";
static constexpr const char *kDescriptorId =
    "398b8a86224185b6c6ca7b2d49bc83861f64f2a8c69afa03fbb430b9077c1f45";
static constexpr const char *kActionId =
    "e621ea9a05da45da4a120c2b68fbdefcad5f4a48274a5ac5290f5fcc25d7c55b";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR|SHA256=398b8a86224185b6c6ca7b2d49bc83861f64f2a8c69afa03fbb430b9077c1f45\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
