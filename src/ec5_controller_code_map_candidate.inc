#pragma once

// Fresh one-screen controller-specific 0..7 map.  The waveform bytes and
// frame are identical to the exact-reference L535 active-global atlas; only
// the firmware/action/NVS identity is new.  CS1 slots are 0..7 while CS2
// slots are 7..0, and the host/photo decoder must preserve that distinction.
#define PF_LAYOUT_NAME \
  "REF_R20_535__CS1_ACTIVE_CS2_COMMENTED__R21_FF704__MAP_V1"
#define PF_CS1_R20_PROFILE "LEGACY_ACTIVE_535"
#define PF_CS2_R20_PROFILE "LEGACY_COMMENTED_535"
#define PF_SOURCE_ROLE \
  "VENDOR_EDP_INIT_COMPLETE_535_TABLES_PLUS_ADJACENT_R21_FF"
#define PF_NAME "L535_ACTIVE_CONTROLLER_MAP_V1"
#define PF_NAME_LOWER "lgamap1"
#define PF_GLOBAL_HEADER_PROFILE "LEGACY_ACTIVE_535"
#define PF_EXPECTED_PROFILE \
  "REF_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535__R21FF__MAP_V1"
#define PF_CONTRACT \
  "e8b0348622884e86bc9d1f629a8055d2b0921018de21469dac398ee50a26ed25"
#define PF_TREAT_BUILD_TAG \
  "MF1750_EC5_CONTROLLER_CODE_MAP_L535_ACTIVE_V1_2026-08-23"
#define PF_TREAT_TEST_ID "EC5-CONTROLLER-CODE-MAP-L535-ACTIVE-V1"
#define PF_TREAT_NVS_NAMESPACE "ccmaplga1"
#define PF_RELEASE_REVISION "V1"
#define PF_TREAT_DESCRIPTOR \
  "823c6dfc71ea44fbfd4e6ab52706615890cc0cb482b0c8e4baba524cc5fc6837"
#define PF_TREAT_ACTION \
  "de90b4c247266a1efab5330f1541d8bf7327207ad7d148bda97a0c9c9f51612e"
#define PF_WHITE_DESCRIPTOR \
  "062b9ca7a50f2805ce1a4cb58bf419129418d0728b9abc4be9443687de1e124b"
#define PF_WHITE_ACTION \
  "c24baf700cf8ce45eedcdcde252728ef4d4fd016c3ceaa1dbef7d76699cfab02"

#if MF1750_LEGACY_GLOBAL_ACTIVE != 1 || \
    MF1750_LEGACY_GLOBAL_COMMENTED != 0
#error "Controller code map V1 requires the active global header"
#endif
