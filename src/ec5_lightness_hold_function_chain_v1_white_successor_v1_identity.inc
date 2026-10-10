#pragma once

// Frozen, compile-visible authority for the independent post-H2 factory-OTP
// white action.  Exactly one source action is accepted: ordinal 5 H2 COMPLETE
// from the sealed lightness/HOLD main application.
static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_lightness_hold_function_chain_v1_white_v1";
static constexpr const char *kCampaignId =
    "EC5_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_FACTORY_OTP_WHITE_SUCCESSOR_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1";
static constexpr const char *kSourceMainContractId =
    "ad14f5394a5c6e284885aa504ea0d99fec0ccb1dcf8053759dba025b8606f3e3";
static constexpr const char *kBuildTag =
    "MF1750_EC5_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_FACTORY_OTP_WHITE_SUCCESSOR_V1_2026-09-01";
static constexpr const char *kContractId =
    "18ed20ebb2906bf6c8cec9c738c183c58c8512c0856083b79be141cb0562244d";
static constexpr const char *kNvsNamespace = "lhfcw_v1";
static constexpr const char *kDescriptorId =
    "d62abfb200d94b9cebc163d4e82e89ccc80fa483cae85e9ab7561f9257e9cf04";
static constexpr const char *kActionId =
    "d731ca688e935d2fec1fa15f24e51126f9a7fd8b3d026f3e41653b11bdd5f972";
static constexpr const char *kAcceptedSourceActionsSha256 =
    "34ce89a89cba4063123b54dc110b37f50a639f639b095738d66712ff98b8a76e";
static constexpr const char *kSourceFirmwareBinSha256 =
    "3f49ba07e497443813f4fb3f5281ed510953ffcfdb8db8a73c4d9466551e30ff";
static constexpr const char *kSourceFirmwareElfSha256 =
    "ded43d84b5897b5793e3f25c84bf96d2118ae775b71bf8a61d5cbe1c1502fd45";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_AFTER_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_H2_COMPLETE|SHA256=d62abfb200d94b9cebc163d4e82e89ccc80fa483cae85e9ab7561f9257e9cf04\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
