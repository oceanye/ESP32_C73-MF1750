#include "ec5_raw_p16_crossover_t2_discovery_successor_identity.inc"

namespace srp = mf1750_raw_p16_crossover_t2_discovery_successor;

static constexpr const char *kClassification = srp::kClassification;
static constexpr const char *kProfileSource = srp::kProfileSource;
static constexpr const char *kIdentityRevision = srp::kIdentityRevision;
static constexpr const char *kDeviceApiVersion = srp::kDeviceApiVersion;
static constexpr const char *kLayoutId = srp::kVariantKey;
static constexpr const char *kBuildTag = srp::kBuildTag;
static constexpr const char *kBootLabel = srp::kBootLabel;
#if defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_BUILD)
static constexpr const char *kBootSummary =
    "One fixed T4 V5 active-header CA matched R20 swap 4x8 full-frame "
    "human-primary confirmation atlas; zero qualified colours";
#elif defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4_BUILD)
static constexpr const char *kBootSummary =
    "One fixed T4 V4 active-header CA matched R20 swap 4x8 full-frame "
    "human-primary confirmation atlas; zero qualified colours";
#elif defined(MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_BUILD)
static constexpr const char *kBootSummary =
    "One fixed T3-AC position-balanced 4x8 full-frame human-primary "
    "profile-following review atlas; camera optional and zero qualified colours";
#else
static constexpr const char *kBootSummary =
    "One fixed T2-CA position-balanced 4x8 full-frame coarse-discovery "
    "atlas; screening-only and zero qualified colours";
#endif
static constexpr const char *kTestId = srp::kTestId;
static constexpr const char *kCampaignId = srp::kCampaignId;
static constexpr const char *kContractId = srp::kContractId;

#if defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_BUILD)
#define MF1750_P16X_KIND_BASE \
  "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-v5"
#define MF1750_P16X_ROUTE_BASE \
  "/api/ec5/raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-v5"
#elif defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4_BUILD)
#define MF1750_P16X_KIND_BASE \
  "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-v4"
#define MF1750_P16X_ROUTE_BASE \
  "/api/ec5/raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-v4"
#elif defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V3_BUILD)
#define MF1750_P16X_KIND_BASE \
  "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-v3"
#define MF1750_P16X_ROUTE_BASE \
  "/api/ec5/raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-v3"
#elif defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V2_BUILD)
#define MF1750_P16X_KIND_BASE \
  "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-v2"
#define MF1750_P16X_ROUTE_BASE \
  "/api/ec5/raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-v2"
#elif defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_V1_BUILD)
#define MF1750_P16X_KIND_BASE \
  "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-v1"
#define MF1750_P16X_ROUTE_BASE \
  "/api/ec5/raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-v1"
#elif defined(MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2_BUILD)
#define MF1750_P16X_KIND_BASE \
  "mf1750-ec5-raw-p16-crossover-t3-ac-profile-following-successor-v2"
#define MF1750_P16X_ROUTE_BASE \
  "/api/ec5/raw-p16-crossover-t3-ac-profile-following-successor-v2"
#elif defined(MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_BUILD)
#define MF1750_P16X_KIND_BASE \
  "mf1750-ec5-raw-p16-crossover-t3-ac-profile-following-successor-v1"
#define MF1750_P16X_ROUTE_BASE \
  "/api/ec5/raw-p16-crossover-t3-ac-profile-following-successor-v1"
#elif defined(MF1750_RAW_P16_CROSSOVER_T2_DISCOVERY_SUCCESSOR_V2_BUILD)
#define MF1750_P16X_KIND_BASE \
  "mf1750-ec5-raw-p16-crossover-t2-ca-coarse-discovery-successor-v2"
#define MF1750_P16X_ROUTE_BASE \
  "/api/ec5/raw-p16-crossover-t2-ca-coarse-discovery-successor-v2"
#else
#define MF1750_P16X_KIND_BASE \
  "mf1750-ec5-raw-p16-crossover-t2-ca-coarse-discovery-successor-v1"
#define MF1750_P16X_ROUTE_BASE \
  "/api/ec5/raw-p16-crossover-t2-ca-coarse-discovery-successor-v1"
#endif

static constexpr const char *kVersionKind = MF1750_P16X_KIND_BASE "-version";
static constexpr const char *kManifestKind = MF1750_P16X_KIND_BASE "-manifest";
static constexpr const char *kStatusKind = MF1750_P16X_KIND_BASE "-status";
static constexpr const char *kReportKind = MF1750_P16X_KIND_BASE "-report";
static constexpr const char *kBaselineRole = srp::kBaselineRole;
#if defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_BUILD) || \
    defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4_BUILD)
#if defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_BUILD)
static constexpr char kV4HostRunnerRejectionAuthorityKey[] =
    "t4_v4_host_runner_rejection";
#define MF1750_P16X_V4V5_CONTAINMENT_SUFFIX \
  "\"w9_clean_white_remains_valid_after_v4_host_rejection\":true," \
  "\"post_t4_v5_fresh_white_successor_required\":true"
#define MF1750_P16X_V4V5_REJECTION_JSON \
  "\"t4_v4_host_runner_rejection\":{" \
  "\"path\":\".test-output/hardware/MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_20260901_V4/action-01-host-runner-rejection-reconciled.json\"," \
  "\"bytes\":28704," \
  "\"file_sha256\":\"650576fa5506f6afe039296262c8bd76e15f73fb3d54aa4675507f36808114bb\"," \
  "\"canonical_integrity_sha256\":\"f4ed665890c9aed8ce8b70b56c8bffb97de4bd47a22ab2c6c8be1fd7141c2049\"," \
  "\"sealed\":true," \
  "\"kind\":\"mf1750-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-v4-host-runner-rejection-not-executed-reconciliation\"," \
  "\"campaign_id\":\"EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4\"," \
  "\"contract_id\":\"3a1c254d2beb0f06deb43781b1e3d9c5e94795c3a1354756c4b1a3ed12824150\"," \
  "\"descriptor_id\":\"3c1ec52d3bc09ac0fde195d8b467e1b844357c3d5bdbc6ce0ea685962242d6d1\"," \
  "\"action_id\":\"c778bc7ccd90fdb2f93abef2aef10ba05d48603bfe790e6f9b6b97dd34b9f154\"," \
  "\"terminal_state\":\"NOT_EXECUTED\"," \
  "\"host_rejected_before_network_claim_arm_execute\":true," \
  "\"network_requests\":0," \
  "\"permanent_claims_created\":0," \
  "\"arm_requests\":0," \
  "\"execute_requests\":0," \
  "\"driver_calls\":0," \
  "\"visible_refreshes\":0," \
  "\"same_boot\":true," \
  "\"w9_clean_white_remains_valid\":true," \
  "\"retry_forbidden\":true},"
#define MF1750_P16X_V4V5_TOMBSTONE_SUFFIX \
  ",\"c778bc7ccd90fdb2f93abef2aef10ba05d48603bfe790e6f9b6b97dd34b9f154\""
#else
#define MF1750_P16X_V4V5_CONTAINMENT_SUFFIX \
  "\"post_t4_v4_fresh_white_successor_required\":true"
#define MF1750_P16X_V4V5_REJECTION_JSON ""
#define MF1750_P16X_V4V5_TOMBSTONE_SUFFIX ""
#endif
static constexpr const char *kExternalWhiteAnchorJson = R"json(
"external_containment":{
  "outside_campaign":true,
  "factory_otp_white_before_required":true,
  "factory_otp_white_after_required":true,
  "completed_w9_machine_white_anchor_present":true,
  "fresh_operator_clean_white_confirmation_required":true,
  "formal_full_panel_white_evidence":false,
  "human_observation_required":true,
  "white_actions_in_campaign":0,
)json" MF1750_P16X_V4V5_CONTAINMENT_SUFFIX R"json(
},
"source_action_authority":{
  "kind":"mf1750-ec5-raw-p16-crossover-t3-ac-profile-following-successor-v2-result",
  "path":".test-output/hardware/MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260831_V2/action-01-position-balanced-atlas.json",
  "bytes":64782,
  "file_sha256":"e7ba8d10f5428372e0462835274cfdebeef5f19d0b8ab354fdcdfadf534a4ec3",
  "canonical_integrity_sha256":"4070a4381d7641f98bef0c84ed2fc2f885a5795ba43599f62812d9e4918c2b4e",
  "campaign_id":"EC5_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2",
  "contract_id":"cc33b55a64fc2d54884f9c6ca65e117d6767fab0f0c60c3e5f55fac3554e5729",
  "descriptor_id":"c2e40c4c59cf6cca3f6ff4fd8c568a5ddee59e8c2100a9cf5d50c007317a148a",
  "action_id":"73f6e97b49b5bd8c46edbba9edffde99967dcb170be6150082dc7c68100fada5",
  "profile_id":"LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535",
  "global_header":"active",
  "cs1_profile":"active",
  "cs2_profile":"commented",
  "outcome":"complete_pass",
  "terminal_state":"COMPLETE",
  "visible_refreshes":1
},
"pre_white_action_evidence":{
  "kind":"mf1750-raw-p16-crossover-w9-w8-arm400-successor-white-v1-result",
  "path":".test-output/hardware/MF1750_RAW_P16_CROSSOVER_W9_W8_ARM400_SUCCESSOR_WHITE_20260831_V1/action-01-factory-otp-white.json",
  "bytes":29040,
  "file_sha256":"26ef448478d5680a19869ffbb0982cfb65db14e6bd20880961eb021a0d90097a",
  "canonical_integrity_sha256":"2c6c818300dc0f72f01607fefaae2467d816ff449c64daa3c8eadb26510bd350",
  "campaign_id":"EC5_RAW_P16_CROSSOVER_W9_AFTER_W8_ARM400_SUCCESSOR_FACTORY_OTP_WHITE_V1",
  "contract_id":"33cdb659c99b89808fda9679b559b1ad76b4326e66d08274caceb7d77f2dfba5",
  "descriptor_id":"a5f01dd65e9956109c47d4564446f3cf104085999a0b017189a3a93fcf06fe1d",
  "action_id":"72c7ab97a607aacf42c2bbe3bc8f5ac121489cfc3e47ca0fb978f04f698f5910",
  "outcome":"complete_pass",
  "terminal_state":"COMPLETE",
  "visible_refreshes":1
},
"t4_v3_terminal_fault":{
  "path":".test-output/hardware/MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_20260831_V3/action-01-terminal-read-only-salvage-reconciled.json",
  "bytes":54647,
  "file_sha256":"d1c5b1dbdc67712703dd64bbdff7ebc9c9d862789f6db398714c4b0d7cc28e5c",
  "canonical_integrity_sha256":"3c59ad53160a85cf6d9a4493e909d2f0d2507940b6e859a587fb06df3a6bfe79",
  "action_id":"90d769f4e139829bd5aed23ae03aa831be8b4b67159a3463f8747dbeb2c2baee",
  "outcome":"fault_salvaged_read_only",
  "terminal_state":"FAULT",
  "driver_calls":1,
  "retry_forbidden":true
},
"w9_permanent_claim":{
  "path":".test-output/hardware/.mf1750_raw_p16_crossover_w9_w8_arm400_successor_white_v1_claims/72c7ab97a607aacf42c2bbe3bc8f5ac121489cfc3e47ca0fb978f04f698f5910.json",
  "bytes":1834,
  "file_sha256":"beabfecebc4afbe7411eda1bfc088b0e7537b87a997e9da7db33129cc0d4b708",
  "canonical_integrity_sha256":"77f8a337b5197b89e8d78dc6b205f620fa0da80aff5f37a39064a161be27e80c",
  "action_id":"72c7ab97a607aacf42c2bbe3bc8f5ac121489cfc3e47ca0fb978f04f698f5910",
  "state":"permanently_claimed_after_j2_on_preflight_before_first_arm",
  "write_contract":"O_EXCL",
  "permanently_consumed":true
},
"w9_post_white_protective_off":{
  "path":".test-output/hardware/MF1750_RAW_P16_CROSSOVER_W9_W8_ARM400_SUCCESSOR_WHITE_20260831_V1/relay-post-white-protective-off.json",
  "bytes":1802,
  "file_sha256":"0af2b5b0725d0eb0bb3738882a0b772165a1cf17f45599d19d92976679f41033",
  "canonical_integrity_sha256":"488533e223ac2f9021368f9762c1bf05c393f5bb47be706af882fb3fb57ea368",
  "commanded_state":"OFF",
  "target_state":"OFF",
  "off_gate_passed":true,
  "electrical_state_proven":false
},
"operator_gnd_assertion":{
  "kind":"mf1750-operator-gnd-reseat-assertion-v1",
  "fault_cause_verbatim":"果然是GND掉了",
  "reseat_and_repower_verbatim":"插座gnd都ok，重新上电检查一下",
  "post_reseat_normal_verbatim":"是的，一切正常",
  "gnd_reseated_and_powered_check_reported_normal":true,
  "conversation_assertion_only":true,
  "cryptographic_evidence":false,
  "electrical_state_proven":false,
  "does_not_reclassify_t4_v3_fault":true
},
)json" MF1750_P16X_V4V5_REJECTION_JSON R"json(
"non_reusable_action_ids":[
  "73ff6d58686acdd88929b9c0d9e983818c75abb7ad7f1ccebf34219dd82a7c72",
  "d38f77df0f02d1eb65641d2b8836bce46db2b563b75d711d86b2da1ebe989470",
  "4a7c3d2816aca50e124049e048c7d7dbeec32a8c7bb825b9cd5294fdd23f144a",
  "f8cf26e3c344d78ddebd06a570ad19f7cad879cf8b5d6d3f9ce620e86bd850a5",
  "b0c81939e444c2e9d062e9d54850604409d89e81d59b521f28f8f46c1d456a4f",
  "c8e00dcb3a5d3bff11c192b56d7fc3074605be561fec1fb5688a065444365c63",
  "6ca102bdd7190cba9e524a7d8d8afa0fd6f1e57a73cb913d55aa40976912383a",
  "26265cb3f26a9ae9f0b106822d163bad6cdc9776d18618726064729bcb280f6a",
  "c184e610cc2ac464ca152eb1af7a0a9f746e5d92c38da53b673de9c0dcdcfd1f",
  "b37e6e5846eecff74b0d478dcdcf5223cdb20f2aa794a2b7f264c42bc21a87e9",
  "db009936f341cd612be9aa47d08a0a316ec2c581c3c88d35d089ce3fa5857104",
  "73f6e97b49b5bd8c46edbba9edffde99967dcb170be6150082dc7c68100fada5",
  "7d600b1a0072a1966e5240dec8756094962066d2ebd3fff555af2d93da3407f4",
  "c9a88f5b4cae0589279d3d874f81492c17d6ba4afc2f5da256fec56bec9b36a1",
  "399a0ec181ece961b25b3de630ae1c313e2855d65d1036459f22aec16bf174b5",
  "90d769f4e139829bd5aed23ae03aa831be8b4b67159a3463f8747dbeb2c2baee",
  "46f0ee263d7d6e2759d0078ba523878f29bf095bab4f9928288c9ccf76d1c348",
  "72c7ab97a607aacf42c2bbe3bc8f5ac121489cfc3e47ca0fb978f04f698f5910"
)json" MF1750_P16X_V4V5_TOMBSTONE_SUFFIX R"json(
],
"human_observation_plan":{
  "primary_judgement":"HUMAN_VISUAL_MATCHED_R20_SWAP_CONFIRMATION_REVIEW",
  "operator_observation_required":true,
  "camera_required_for_decision":false,
  "camera_evidence_optional":true,
  "camera_evidence_only":true,
  "required_retained_camera_frame_count":0,
  "absolute_colour_claimed":false,
  "stable_new_colour_claimed":false,
  "profile_following_proven_by_this_action":false,
  "matched_swap_confirmation_earned_before_observation":false,
  "qualified_colour_count":0
}
)json";
#undef MF1750_P16X_V4V5_CONTAINMENT_SUFFIX
#undef MF1750_P16X_V4V5_REJECTION_JSON
#undef MF1750_P16X_V4V5_TOMBSTONE_SUFFIX
#elif defined(MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_BUILD)
#if defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_V1_BUILD) || \
    defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V3_BUILD) || \
    defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V2_BUILD)
static constexpr const char *kExternalWhiteAnchorJson =
    "\"external_containment\":{" 
    "\"outside_campaign\":true,"
    "\"factory_otp_white_before_required\":true,"
    "\"factory_otp_white_after_required\":true,"
    "\"completed_w4_machine_white_anchor_present\":true,"
    "\"fresh_operator_clean_white_confirmation_required\":true,"
    "\"formal_full_panel_white_evidence\":false,"
    "\"human_observation_required\":true,"
    "\"white_actions_in_campaign\":0},"
    "\"source_action_authority\":{" 
    "\"kind\":\"mf1750-ec5-raw-p16-crossover-t3-ac-profile-following-successor-v2-result\","
    "\"path\":\".test-output/hardware/MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260831_V2/action-01-position-balanced-atlas.json\","
    "\"bytes\":64782,"
    "\"file_sha256\":\"e7ba8d10f5428372e0462835274cfdebeef5f19d0b8ab354fdcdfadf534a4ec3\","
    "\"canonical_integrity_sha256\":\"4070a4381d7641f98bef0c84ed2fc2f885a5795ba43599f62812d9e4918c2b4e\","
    "\"campaign_id\":\"EC5_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2\","
    "\"contract_id\":\"cc33b55a64fc2d54884f9c6ca65e117d6767fab0f0c60c3e5f55fac3554e5729\","
    "\"descriptor_id\":\"c2e40c4c59cf6cca3f6ff4fd8c568a5ddee59e8c2100a9cf5d50c007317a148a\","
    "\"action_id\":\"73f6e97b49b5bd8c46edbba9edffde99967dcb170be6150082dc7c68100fada5\","
    "\"profile_id\":\"LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535\","
    "\"global_header\":\"active\","
    "\"cs1_profile\":\"active\",\"cs2_profile\":\"commented\","
    "\"outcome\":\"complete_pass\",\"terminal_state\":\"COMPLETE\","
    "\"visible_refreshes\":1},"
    "\"pre_white_action_evidence\":{" 
    "\"kind\":\"mf1750-raw-p16-crossover-w4-t3-ac-profile-following-successor-v2-white-result\","
    "\"path\":\".test-output/hardware/MF1750_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2_WHITE_20260831_V1/action-01-factory-otp-white.json\","
    "\"bytes\":30300,"
    "\"file_sha256\":\"11196c4cc5dade801d99b647e08fcccee02521acfbe0d3785c77d05a4697fb98\","
    "\"canonical_integrity_sha256\":\"74ff3af94ebb4c2f58270d7cd9672a359b2e21332149a8a422feaa3967fd753d\","
    "\"campaign_id\":\"EC5_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2_WHITE_V1\","
    "\"contract_id\":\"a75af9d7fcfc425ffff18f08d2c6f59eec61b1a4e8e53a3c18bcf2783767e6bb\","
    "\"descriptor_id\":\"45e796933c4006b6b7afa050e2a4ba25fd9d78a922bf00ba11f0193002909e04\","
    "\"action_id\":\"7d600b1a0072a1966e5240dec8756094962066d2ebd3fff555af2d93da3407f4\","
    "\"source_action_id\":\"73f6e97b49b5bd8c46edbba9edffde99967dcb170be6150082dc7c68100fada5\","
    "\"outcome\":\"complete_pass\",\"terminal_state\":\"COMPLETE\","
    "\"visible_refreshes\":1,\"formal_full_panel_white_evidence\":false,"
    "\"fresh_operator_clean_white_confirmation_required\":true},"
    "\"non_reusable_action_ids\":["
    "\"73ff6d58686acdd88929b9c0d9e983818c75abb7ad7f1ccebf34219dd82a7c72\","
    "\"d38f77df0f02d1eb65641d2b8836bce46db2b563b75d711d86b2da1ebe989470\","
    "\"4a7c3d2816aca50e124049e048c7d7dbeec32a8c7bb825b9cd5294fdd23f144a\","
    "\"f8cf26e3c344d78ddebd06a570ad19f7cad879cf8b5d6d3f9ce620e86bd850a5\","
    "\"b0c81939e444c2e9d062e9d54850604409d89e81d59b521f28f8f46c1d456a4f\","
    "\"c8e00dcb3a5d3bff11c192b56d7fc3074605be561fec1fb5688a065444365c63\","
    "\"6ca102bdd7190cba9e524a7d8d8afa0fd6f1e57a73cb913d55aa40976912383a\","
    "\"26265cb3f26a9ae9f0b106822d163bad6cdc9776d18618726064729bcb280f6a\","
    "\"c184e610cc2ac464ca152eb1af7a0a9f746e5d92c38da53b673de9c0dcdcfd1f\","
    "\"b37e6e5846eecff74b0d478dcdcf5223cdb20f2aa794a2b7f264c42bc21a87e9\","
    "\"db009936f341cd612be9aa47d08a0a316ec2c581c3c88d35d089ce3fa5857104\","
    "\"73f6e97b49b5bd8c46edbba9edffde99967dcb170be6150082dc7c68100fada5\"," 
#if defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V3_BUILD)
    "\"7d600b1a0072a1966e5240dec8756094962066d2ebd3fff555af2d93da3407f4\","
    "\"c9a88f5b4cae0589279d3d874f81492c17d6ba4afc2f5da256fec56bec9b36a1\","
    "\"399a0ec181ece961b25b3de630ae1c313e2855d65d1036459f22aec16bf174b5\"],"
#else
    "\"7d600b1a0072a1966e5240dec8756094962066d2ebd3fff555af2d93da3407f4\"],"
#endif
    "\"human_observation_plan\":{" 
    "\"primary_judgement\":\"HUMAN_VISUAL_MATCHED_R20_SWAP_CONFIRMATION_REVIEW\","
    "\"operator_observation_required\":true,"
    "\"camera_required_for_decision\":false,"
    "\"camera_evidence_optional\":true,\"camera_evidence_only\":true,"
    "\"required_retained_camera_frame_count\":0,"
    "\"absolute_colour_claimed\":false,"
    "\"stable_new_colour_claimed\":false,"
    "\"profile_following_proven_by_this_action\":false,"
    "\"matched_swap_confirmation_earned_before_observation\":false,"
    "\"qualified_colour_count\":0}";
#else
static constexpr const char *kExternalWhiteAnchorJson =
    "\"external_containment\":{" 
    "\"outside_campaign\":true,"
    "\"factory_otp_white_before_required\":true,"
    "\"factory_otp_white_after_required\":true,"
    "\"off_white_photos_before_atlas_required\":0,"
    "\"off_retained_atlas_photos_required\":0,"
    "\"camera_evidence_optional\":true,"
    "\"post_white_clean_visual_gate_required\":true,"
    "\"human_observation_required\":true,"
    "\"white_actions_in_campaign\":0},"
    "\"source_action_authority\":{" 
    "\"kind\":\"mf1750-ec5-raw-p16-crossover-t2-ca-coarse-discovery-successor-v2-result\","
    "\"path\":\".test-output/hardware/MF1750_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_20260830_V2/action-01-position-balanced-atlas.json\","
    "\"bytes\":46464,"
    "\"file_sha256\":\"490df32422ec362f20c09e40d60d1e86e3f8bb46e9820f624004a4f07d08a989\","
    "\"canonical_integrity_sha256\":\"a7fc644e46586a5ebe8a1d447062a0ad6b0db8b8c2121ca61c3d842980e6bbcb\","
    "\"campaign_id\":\"EC5_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_V2\","
    "\"contract_id\":\"3a9dc65fcc4985cbb27195c340e910e7531b118cd8279a52dac9b49ce9558b77\","
    "\"descriptor_id\":\"e80021a5d42db51180cd95873d48d979d70c6881c1dd8642b2c5b7299f126e65\","
    "\"action_id\":\"c184e610cc2ac464ca152eb1af7a0a9f746e5d92c38da53b673de9c0dcdcfd1f\","
    "\"outcome\":\"complete_pass\",\"terminal_state\":\"COMPLETE\","
    "\"round\":2,\"visible_refreshes\":1},"
    "\"pre_white_action_evidence\":{" 
    "\"kind\":\"mf1750-raw-p16-crossover-w3-t2-discovery-successor-v2-white-result\"," 
    "\"path\":\".test-output/hardware/MF1750_RAW_P16_CROSSOVER_W3_T2_DISCOVERY_SUCCESSOR_V2_WHITE_20260830_V1/action-01-factory-otp-white.json\","
    "\"bytes\":29734,"
    "\"file_sha256\":\"445181448ab4ff7bdd19d646cff24f3dd8fec89b329512b9f90ad6c3b2d257ef\","
    "\"canonical_integrity_sha256\":\"624df0db0c082a151f54a051ca45209f4114b67a1643c358269d3efe444d611f\","
    "\"campaign_id\":\"EC5_RAW_P16_CROSSOVER_W3_AFTER_T2_COARSE_DISCOVERY_SUCCESSOR_V2_WHITE_V1\","
    "\"contract_id\":\"69be4f9fa69df03d861b1de6f01e289aca492fd4ad87a5ea1ef18f99dc2516a4\","
    "\"descriptor_id\":\"5f14f576721f5f4143f7a577d92bc97d4ce5646aa98bc3f4edb52cfb9da7b24f\","
    "\"action_id\":\"b37e6e5846eecff74b0d478dcdcf5223cdb20f2aa794a2b7f264c42bc21a87e9\"," 
    "\"source_action_id\":\"c184e610cc2ac464ca152eb1af7a0a9f746e5d92c38da53b673de9c0dcdcfd1f\"," 
    "\"outcome\":\"complete_pass\",\"terminal_state\":\"COMPLETE\"," 
    "\"visible_refreshes\":1},"
    "\"pre_white_authority\":{" 
    "\"kind\":\"mf1750-raw-p16-crossover-clean-white-human-observation-v1\"," 
    "\"path\":\".test-output/hardware/MF1750_RAW_P16_CROSSOVER_W3_T2_DISCOVERY_SUCCESSOR_V2_WHITE_20260830_V1/human-clean-white-authority-v1.json\"," 
    "\"bytes\":4072,"
    "\"file_sha256\":\"5f5ff9d0c6bc023c461038e17fbc92b0fda5b475d52019bf736b91d745d5582b\"," 
    "\"canonical_integrity_sha256\":\"2fceccd9cac4af23ffc0d27f7d14a546920d586cc0efd72f0799037cdb5b614f\"," 
    "\"stage\":\"w3-after-t2-coarse-discovery-successor-v2\"," 
    "\"action_result_binding\":{" 
    "\"campaign_id\":\"EC5_RAW_P16_CROSSOVER_W3_AFTER_T2_COARSE_DISCOVERY_SUCCESSOR_V2_WHITE_V1\"," 
    "\"contract_id\":\"69be4f9fa69df03d861b1de6f01e289aca492fd4ad87a5ea1ef18f99dc2516a4\"," 
    "\"descriptor_id\":\"5f14f576721f5f4143f7a577d92bc97d4ce5646aa98bc3f4edb52cfb9da7b24f\"," 
    "\"action_id\":\"b37e6e5846eecff74b0d478dcdcf5223cdb20f2aa794a2b7f264c42bc21a87e9\"," 
    "\"source_action_id\":\"c184e610cc2ac464ca152eb1af7a0a9f746e5d92c38da53b673de9c0dcdcfd1f\"," 
    "\"bytes\":29734,"
    "\"file_sha256\":\"445181448ab4ff7bdd19d646cff24f3dd8fec89b329512b9f90ad6c3b2d257ef\"," 
    "\"canonical_integrity_sha256\":\"624df0db0c082a151f54a051ca45209f4114b67a1643c358269d3efe444d611f\"},"
    "\"raw_operator_report\":{\"operator_verbatim\":\"白屏，干净\"},"
    "\"authority\":{" 
    "\"operator_reported_clean_white\":true,"
    "\"action_complete_exactly_bound\":true,"
    "\"final_relay_commanded_off_exactly_bound\":true,"
    "\"final_relay_off_is_command_query_not_load_voltage_proof\":true,"
    "\"operator_verbatim_preserved\":true,"
    "\"automatic_next_action_authorized\":false,"
    "\"camera_confirmation_claimed\":false,"
    "\"colorimeter_confirmation_claimed\":false,"
    "\"formal_colour_gate_evaluated\":false},"
    "\"final_relay_off_receipt_binding\":{" 
    "\"path\":\".test-output/hardware/MF1750_RAW_P16_CROSSOVER_W3_T2_DISCOVERY_SUCCESSOR_V2_WHITE_20260830_V1/relay-post-action-protective-off-20260830-204303.json\"," 
    "\"bytes\":1807,"
    "\"file_sha256\":\"febbab71fcbca53130179424775caf6245990d6098f4fab8a1478474b537bae1\"," 
    "\"canonical_integrity_sha256\":\"7ec1be01d29a543962db54f18037e09c9f52f060f62ef115fc0e830a5989c3ad\"," 
    "\"commanded_state\":\"OFF\",\"target_state\":\"OFF\"," 
    "\"off_gate_passed\":true,\"electrical_state_proven\":false},"
    "\"output_write_contract\":\"O_EXCL\"," 
    "\"offline_execution\":{" 
    "\"camera_accessed\":false,\"display_refreshed\":false,"
    "\"firmware_flashed\":false,\"hardware_accessed\":false,"
    "\"network_accessed\":false,\"relay_accessed\":false,"
    "\"serial_or_com_accessed\":false}},"
    "\"non_reusable_action_ids\":["
    "\"73ff6d58686acdd88929b9c0d9e983818c75abb7ad7f1ccebf34219dd82a7c72\","
    "\"d38f77df0f02d1eb65641d2b8836bce46db2b563b75d711d86b2da1ebe989470\","
    "\"4a7c3d2816aca50e124049e048c7d7dbeec32a8c7bb825b9cd5294fdd23f144a\","
    "\"f8cf26e3c344d78ddebd06a570ad19f7cad879cf8b5d6d3f9ce620e86bd850a5\","
    "\"b0c81939e444c2e9d062e9d54850604409d89e81d59b521f28f8f46c1d456a4f\","
    "\"c8e00dcb3a5d3bff11c192b56d7fc3074605be561fec1fb5688a065444365c63\","
    "\"6ca102bdd7190cba9e524a7d8d8afa0fd6f1e57a73cb913d55aa40976912383a\","
    "\"26265cb3f26a9ae9f0b106822d163bad6cdc9776d18618726064729bcb280f6a\"," 
    "\"c184e610cc2ac464ca152eb1af7a0a9f746e5d92c38da53b673de9c0dcdcfd1f\"," 
#if !defined(MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2_BUILD)
    "\"b37e6e5846eecff74b0d478dcdcf5223cdb20f2aa794a2b7f264c42bc21a87e9\"],"
    "\"human_observation_plan\":{" 
    "\"primary_judgement\":\"HUMAN_VISUAL_PROFILE_FOLLOWING_REVIEW\"," 
    "\"operator_observation_required\":true,"
    "\"camera_required_for_decision\":false,"
    "\"camera_evidence_optional\":true,\"camera_evidence_only\":true,"
    "\"required_retained_camera_frame_count\":0,"
    "\"absolute_colour_claimed\":false,"
    "\"stable_new_colour_claimed\":false,"
    "\"profile_following_proven_by_this_action\":false,"
    "\"qualified_colour_count\":0}";
#else
    "\"b37e6e5846eecff74b0d478dcdcf5223cdb20f2aa794a2b7f264c42bc21a87e9\"," 
    "\"db009936f341cd612be9aa47d08a0a316ec2c581c3c88d35d089ce3fa5857104\"],"
    "\"v1_terminal_failure_authority\":{"
    "\"kind\":\"mf1750-raw-p16-crossover-t3-ac-profile-following-successor-v1-terminal-failure-authority\"," 
    "\"predecessor_campaign_id\":\"EC5_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V1\"," 
    "\"predecessor_contract_id\":\"714ddf2e44725361e9b404ce512d9c9a96a96d7b31cce8bfbd4555d0883e9e19\"," 
    "\"predecessor_descriptor_id\":\"52de5c169b19bf7db2788f73e2c450971bb6adffb7c305cb0dd8d7873b9b3af9\"," 
    "\"predecessor_action_id\":\"db009936f341cd612be9aa47d08a0a316ec2c581c3c88d35d089ce3fa5857104\"," 
    "\"flash_evidence\":{"
    "\"path\":\".test-output/hardware/MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260830_V1/app-only-single-boot-flash.json\"," 
    "\"bytes\":7069,"
    "\"file_sha256\":\"d72f41f9af347437a394e19cd59759a7331a4aa5496ee74cf84123992788897c\"," 
    "\"canonical_integrity_sha256\":\"c26d53af7c7acba53fc5f6728acddcda88be17ba4b3d73e7c9073d6817987699\"," 
    "\"outcome\":\"app_only_write_verify_single_boot_pass\"},"
    "\"failed_diagnostic_evidence\":{"
    "\"path\":\".test-output/hardware/MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260830_V1/j2-off-diagnostic.json\"," 
    "\"bytes\":2112,"
    "\"file_sha256\":\"8bd0510a539a93d7a0d4740dd550c8d0535f06805061e7ee8708a944d63ae738\"," 
    "\"canonical_integrity_sha256\":\"9fd138531d6ee762313904d30f86d26549a2519a43ea026a4c9c23f387f20194\"," 
    "\"outcome\":\"j2_off_diagnostic_failed_no_claim\"," 
    "\"network_get\":1,\"network_post\":0,"
    "\"permanent_claims_created\":0,\"visible_refreshes\":0},"
    "\"final_relay_off_evidence\":{"
    "\"path\":\".test-output/hardware/MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260830_V1/relay-post-diagnostic-failure-off-query-20260831-133811130.json\"," 
    "\"bytes\":1248,"
    "\"file_sha256\":\"345973ac5bde6f4488d66279f7072479512c4edbf1c8339b3af374b2f0ab49db\"," 
    "\"canonical_integrity_sha256\":\"09975b2f3076f229f7f6b058cb9ea65f77107f075e2c3a90e8875999fc1f5231\"," 
    "\"commanded_state\":\"OFF\",\"off_gate_passed\":true,"
    "\"electrical_state_proven\":false},"
    "\"predecessor_action_output_absent_required\":true,"
    "\"predecessor_claim_absent_required\":true,"
    "\"predecessor_action_never_claimed_or_executed\":true,"
    "\"not_retry_of_predecessor\":true,"
    "\"does_not_reauthorize_v1\":true},"
    "\"address_resolution_boundary\":{"
    "\"kind\":\"mf1750-raw-p16-crossover-t3-ac-profile-following-successor-v2-passive-address-resolution-boundary\"," 
    "\"evidence\":{"
    "\"path\":\".test-output/hardware/MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260831_V2_PREP/passive-ipv4-mac-candidate-binding.json\"," 
    "\"bytes\":2850,"
    "\"file_sha256\":\"4c2fe6c04c90119a776099a187340fa91f8e7cb0b92482ada232af201ebe8fd8\"," 
    "\"canonical_integrity_sha256\":\"704866219593232cfa737b2fd9134d4d305722d764d3a3024af42a0242628dbf\"},"
    "\"v1_failed_base_url_ipv4_is_host_owned\":\"192.168.1.7\"," 
    "\"passive_candidate_ipv4\":\"192.168.1.11\"," 
    "\"passive_candidate_mac\":\"A4-CB-8F-D9-FC-D4\"," 
    "\"passive_neighbour_state\":\"STALE\"," 
    "\"passive_network_layer_mac_binding_observed\":true,"
    "\"fresh_binding_proven\":false,"
    "\"device_application_identity_proven\":false,"
    "\"candidate_is_default_base_url\":false,"
    "\"live_base_url_must_be_explicit\":true,"
    "\"fresh_exact_binding_required_before_future_live_io\":true,"
    "\"does_not_authorize_network_or_device_io\":true},"
    "\"human_observation_plan\":{" 
    "\"primary_judgement\":\"HUMAN_VISUAL_PROFILE_FOLLOWING_REVIEW\","
    "\"operator_observation_required\":true,"
    "\"camera_required_for_decision\":false,"
    "\"camera_evidence_optional\":true,\"camera_evidence_only\":true,"
    "\"required_retained_camera_frame_count\":0,"
    "\"absolute_colour_claimed\":false,"
    "\"stable_new_colour_claimed\":false,"
    "\"profile_following_proven_by_this_action\":false,"
    "\"qualified_colour_count\":0}";
#endif
#endif
#else
static constexpr const char *kExternalWhiteAnchorJson =
    "\"external_containment\":{"
    "\"outside_campaign\":true,"
    "\"factory_otp_white_before_required\":true,"
    "\"factory_otp_white_after_required\":true,"
    "\"off_white_photos_before_atlas_required\":1,"
    "\"off_retained_atlas_photos_required\":3,"
    "\"post_white_clean_visual_gate_required\":true,"
    "\"white_actions_in_campaign\":0},"
    "\"coarse_discovery_authority\":{"
    "\"kind\":\"mf1750-raw-p16-crossover-t1-white-normalized-coarse-screen-v1\","
    "\"path\":\".test-output/hardware/MF1750_RAW_P16_CROSSOVER_T1_AC_20260830_V1/T1.white-normalized-coarse-screen-v1.json\","
    "\"bytes\":293550,"
    "\"file_sha256\":\"4abbcf56bfb390e8cfb394f67eb8d6209fc35d845d1b096b096234973f4f50ea\","
    "\"canonical_integrity_sha256\":\"3b080f2288c45f0ac5cdba9023b90a4f320d4b514bedece2372b72cf6b39d8ad\","
    "\"screening_only\":true,"
    "\"eligible_for_t2_discovery\":true,"
    "\"formal_gate_evaluated\":false,"
    "\"formal_advance_to_t2_permitted\":false,"
    "\"qualified_colour_count\":0,"
    "\"does_not_reverse_consumed_t1\":true}"
#if defined(MF1750_RAW_P16_CROSSOVER_T2_DISCOVERY_SUCCESSOR_V2_BUILD)
    ",\"repeat_authority\":{"
    "\"kind\":\"mf1750-raw-p16-crossover-t2-discovery-successor-white-normalized-coarse-screen-v1\","
    "\"path\":\".test-output/hardware/MF1750_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_20260830_V1/T2.white-normalized-coarse-screen-v1.json\","
    "\"bytes\":187744,"
    "\"file_sha256\":\"de4e790fd3ccb23314eec977b404eee74e7b937dc7522f195bcf07114ef2e856\","
    "\"canonical_integrity_sha256\":\"8e55cc7910c8b879abb050be97f84acf94b8a9e5c345f2537dd47a715daf4c4d\","
    "\"state\":\"T2_SUCCESSOR_COARSE_SCREEN_NOT_ALL_PASS\","
    "\"underexposed_measurement_only\":true,"
    "\"visible_payload_failure_claimed\":false,"
    "\"authorizes_fresh_discovery_repeat_only\":true,"
    "\"exposure\":-3,"
    "\"white_reference_min_lstar\":25.0,"
    "\"automatic_threshold_relaxation\":false}"
#endif
    ;
#endif
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"grid_rows\":4,\"grid_columns_per_controller\":8,"
    "\"row_codes\":[[0,1,2,3,4,5,6,7],[6,7,0,1,2,3,4,5],"
    "[5,4,7,6,1,0,3,2],[3,2,5,4,7,6,1,0]],"
    "\"grid_x0_local\":20,\"grid_y_by_row\":[44,180,316,452],"
    "\"grid_x1_local_exclusive\":492,\"grid_y1_exclusive\":552,"
    "\"cell_width\":52,\"cell_height\":100,\"gap_x\":8,\"gap_y\":36,"
    "\"background_code\":7,\"border\":false,"
    "\"same_layout_both_controllers\":true,"
    "\"controller_dtm_byte_identical\":true,"
    "\"controller_r20_payloads_byte_identical\":false,"
    "\"cs2_position_mirrored\":false,\"spatial_dither\":false,"
    "\"factory_otp_white_ordinals\":[],\"runtime_lut_ordinals\":[1],"
    "\"one_visible_refresh_per_action\":true,"
    "\"samples_per_code_per_controller_per_frame\":4,"
    "\"primary_codes\":[3,5,6,7],\"guard_codes\":[4],"
    "\"control_codes\":[0,1,2],\"qualified_colours\":0,"
    "\"colour_equivalence_claimed\":false,"
    "\"controller_bus_capture_claimed\":false}";
#if defined(MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_BUILD)
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x83\":false,\"command_0x86\":false,"
    "\"unknown_commands\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,\"full_screen_global_refresh\":true,"
    "\"same_r20_controller_parity_probe\":false,"
    "\"crossover_r20_position_balanced_probe\":true,"
    "\"position_balanced_atlas\":true,\"same_palette_hold_probe\":false,"
    "\"cross_palette_hold_probe\":false,\"local_hold_claimed\":false,"
    "\"colour_qualification\":false,\"coarse_discovery_only\":false,"
    "\"profile_following_review_only\":true,"
    "\"profile_following_proven\":false,"
    "\"human_primary_judgement_required\":true,"
    "\"formal_gate_evaluated\":false,\"qualified_colour_count\":0,"
    "\"human_observation_gate_after_every_action\":true,"
    "\"busy_qualified_arm_execute_dispatch\":true,"
    "\"main_campaign_resume_after_containment\":false,"
    "\"device_enforced_same_boot\":true";
#else
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x83\":false,\"command_0x86\":false,"
    "\"unknown_commands\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,\"full_screen_global_refresh\":true,"
    "\"same_r20_controller_parity_probe\":false,"
    "\"crossover_r20_position_balanced_probe\":true,"
    "\"position_balanced_atlas\":true,\"same_palette_hold_probe\":false,"
    "\"cross_palette_hold_probe\":false,\"local_hold_claimed\":false,"
    "\"colour_qualification\":false,\"coarse_discovery_only\":true,"
    "\"formal_gate_evaluated\":false,"
    "\"formal_advance_to_t2_permitted\":false,"
    "\"human_observation_gate_after_every_action\":false,"
    "\"busy_qualified_arm_execute_dispatch\":true,"
    "\"main_campaign_resume_after_containment\":false,"
    "\"device_enforced_same_boot\":true";
#endif

static constexpr const char *kNvsNamespace = srp::kNvsNamespace;
static constexpr const char *kNvsKey = srp::kNvsKey;
static constexpr const char *kNvsBootKey = srp::kNvsBootKey;
static constexpr const char *kVersionRoute = MF1750_P16X_ROUTE_BASE "/version";
static constexpr const char *kManifestRoute =
    MF1750_P16X_ROUTE_BASE "/manifest";
static constexpr const char *kStatusRoute = MF1750_P16X_ROUTE_BASE "/status";
static constexpr const char *kReportRoute = MF1750_P16X_ROUTE_BASE "/report";
static constexpr const char *kArmRoute = MF1750_P16X_ROUTE_BASE "/arm";
static constexpr const char *kExecuteRoute = MF1750_P16X_ROUTE_BASE "/execute";

static constexpr const char *kBuildHeader = "X-EC5-Build-Tag";
static constexpr const char *kTestHeader = "X-EC5-Test-Id";
static constexpr const char *kCampaignHeader = "X-EC5-Campaign-Id";
static constexpr const char *kActionHeader = "X-EC5-Action-Id";
static constexpr const char *kOrdinalHeader = "X-EC5-Ordinal";
static constexpr const char *kDescriptorHeader = "X-EC5-Descriptor-Id";
static constexpr const char *kBootNonceHeader = "X-EC5-Boot-Nonce";
static constexpr const char *kArmNonceHeader = "X-EC5-Arm-Nonce";
static constexpr const char *kIntentHeader = "X-EC5-Intent";
static constexpr const char *kArmIntent = srp::kArmIntent;
static constexpr const char *kExecuteIntent = srp::kExecuteIntent;

static constexpr ActionDescriptor kActions[] = {{
    1,
    EpdChromaGridRole::Source,
    srp::kRole,
    srp::kRound,
    srp::kBranch,
    srp::kDescriptorId,
    srp::kActionId,
#if defined(MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_BUILD)
    srp::kPriorActionId,
#else
    nullptr,
#endif
    srp::kFrameSha256,
    srp::kDtmSha256,
    srp::kDtmSha256,
    srp::kFrameFnv1a,
    srp::kDtmFnv1a,
    srp::kDtmFnv1a,
    {41600, 41600, 41600, 41600, 41600, 41600, 41600, 323200},
}};

#undef MF1750_P16X_KIND_BASE
#undef MF1750_P16X_ROUTE_BASE
