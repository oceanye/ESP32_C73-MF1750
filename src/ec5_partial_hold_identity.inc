#pragma once

#ifndef MF1750_PARTIAL_HOLD_VARIANT
#error "MF1750_PARTIAL_HOLD_VARIANT must be defined"
#endif

#if MF1750_PARTIAL_HOLD_VARIANT < 0 || MF1750_PARTIAL_HOLD_VARIANT > 7
#error "MF1750_PARTIAL_HOLD_VARIANT must be 0..7"
#endif

namespace mf1750_partial_hold {

struct Window {
  uint16_t x;
  uint16_t y;
  uint16_t width;
  uint16_t height;
  uint8_t cs1Code;
  uint8_t cs2Code;
};

struct ActionIdentity {
  const char *role;
  const char *branch;
  const char *descriptorId;
  const char *actionId;
  const char *frameSha256;
  const char *cs1DtmSha256;
  const char *cs2DtmSha256;
  uint32_t frameFnv1a;
  uint32_t cs1DtmFnv1a;
  uint32_t cs2DtmFnv1a;
  uint32_t histogram[8];
};

static constexpr uint8_t kVariant = MF1750_PARTIAL_HOLD_VARIANT;
static constexpr uint8_t kRoleCount = 4;
static constexpr uint8_t kActionCount = 5;
static constexpr uint8_t kWhiteCode = 1;
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = kVariant == 3;
static constexpr bool kSeparateCsWindowCommands = kVariant >= 3;
static constexpr bool kPtlwYEndOneMore = kVariant != 5 && kVariant != 7;

#if MF1750_PARTIAL_HOLD_VARIANT == 0
static constexpr const char *kVariantKey = "ACCUMULATE_OVERWRITE";
static constexpr const char *kVariantDescription =
    "two disjoint windows followed by a nested overwrite";
static constexpr const char *kContractId =
    "0bc62f0cabe60981d825d100a5269c34b51c96c156557ba2aaafd7499f5c7fed";
static constexpr const char *kBuildTag =
    "MF1750_EC5_PARTIAL_HOLD_ACCUMULATE_V1_2026-08-22";
static constexpr const char *kTestId = "EC5-PARTIAL-HOLD-ACCUMULATE-V1";
static constexpr const char *kCampaignId = "EC5_PARTIAL_HOLD_ACCUMULATE_V1";
static constexpr const char *kNvsNamespace = "phold_acc_v1";
static constexpr Window kWindows[3] = {
    {48, 96, 160, 144, 3, 3},
    {304, 336, 160, 144, 5, 5},
    {80, 128, 96, 80, 6, 6},
};
static constexpr ActionIdentity kActions[kActionCount] = {
    {"WHITE_BASELINE", "FACTORY_OTP_FULL_WHITE",
     "c950749385437ff3a384b68f410b916d95cba046d31d92f70b49f319f831ad63",
     "984a95b2322220a54f1f629793aacff87450f1395fa583ab914561630ab677fe",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"PATCH_A", "PTLW_RED_DISJOINT_A",
     "23ef6756ccc4b4429c5ed24d624eabb00b29d6937387bafdffb4e8fb8132b9bb",
     "90e8fd7c0d2f03f11bf95b9a1170d3ba7d9f0d21e039fd5ee6b7f7705e8c1015",
     "5c49fba44abc36aca284b691a0ca0fc78f4fd8bf0169dd856307d5f447d6a8a7",
     "60ea54172ebc484db9d36faeb87bcdf2fa1e4ebde7879ab3e792f850aef265aa",
     "60ea54172ebc484db9d36faeb87bcdf2fa1e4ebde7879ab3e792f850aef265aa",
     0xFAA175C5UL, 0x45E756C5UL, 0x45E756C5UL,
     {0, 568320, 0, 46080, 0, 0, 0, 0}},
    {"PATCH_B", "PTLW_BLUE_DISJOINT_B_HOLD_A",
     "9c29a821ad9642fb147564fbf670d1f44ff707957b52710bd8993cbb0f0cdbce",
     "7db74f05b742de3d59083bf780208002c0c8495871ec6e91af26e426428ff875",
     "9c1c095d7f627264d6083718c409d2a4aa2b2bb98761dd6b2e92a2efa8fd6a55",
     "48992a1d5b47a8d8c3e78e62ee08da4506dc09a28c8d4713a6de55b51367de84",
     "48992a1d5b47a8d8c3e78e62ee08da4506dc09a28c8d4713a6de55b51367de84",
     0x0280CDC5UL, 0x9A232EC5UL, 0x9A232EC5UL,
     {0, 522240, 0, 46080, 0, 46080, 0, 0}},
    {"PATCH_C", "PTLW_GREEN_NESTED_OVERWRITE_HOLD_B",
     "30f69397ef884e720da79c2db0202caccd3ac1fe83836d2b762c32b725a8748e",
     "91956dc79b5b7ea35089537c5f3d6fd74093d53a65e0150910a2c4b7bacfa5e8",
     "aa6a03e87567f6c38374bfac1252ae29e5be972bac846492c62a45ef417be672",
     "b83e2e4addf1e5e63473804579942f23828c7ae1a1251cd2b81e3588efc4551c",
     "b83e2e4addf1e5e63473804579942f23828c7ae1a1251cd2b81e3588efc4551c",
     0x530F47C5UL, 0x211299C5UL, 0x211299C5UL,
     {0, 522240, 0, 30720, 0, 46080, 15360, 0}},
    {"WHITE_RECOVERY", "FACTORY_OTP_FULL_WHITE_RECOVERY",
     "1cf0e98a3de203ade9fabe5d9b39a3c5db155d49042ceb89897e6e5e688bb8fd",
     "ca180705ab239dc786ea60b137ba56e3a391100cc15664dcfdd474d67f76ef83",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};
#elif MF1750_PARTIAL_HOLD_VARIANT == 1
static constexpr const char *kVariantKey = "EDGE_GEOMETRY";
static constexpr const char *kVariantDescription =
    "left edge, right edge, and lower safe-bound windows";
static constexpr const char *kContractId =
    "9f531ab5f7b35ea9141499aea918d17324bde67b9a7921261479d2cc36fea063";
static constexpr const char *kBuildTag =
    "MF1750_EC5_PARTIAL_HOLD_EDGES_V1_2026-08-22";
static constexpr const char *kTestId = "EC5-PARTIAL-HOLD-EDGES-V1";
static constexpr const char *kCampaignId = "EC5_PARTIAL_HOLD_EDGES_V1";
static constexpr const char *kNvsNamespace = "phold_edge_v1";
static constexpr Window kWindows[3] = {
    {0, 32, 128, 128, 2, 2},
    {384, 232, 128, 128, 5, 5},
    {192, 440, 128, 144, 3, 3},
};
static constexpr ActionIdentity kActions[kActionCount] = {
    {"WHITE_BASELINE", "FACTORY_OTP_FULL_WHITE",
     "8e9bf69df17c1e27be4794d6f04687a49dc9085fa6724ffddf5373a4fb7f9936",
     "a345f0d015e1cd31eee24866b0206a32681051d2dabd511c11f5b8277d7a0374",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"PATCH_A", "PTLW_LEFT_EDGE_YELLOW",
     "f76e8ef6aa922e188dffe6a432a2b87606f686178e2e211702222059c93005d3",
     "32c2c9dde18639c164f658176b968d858585da061b6938a3229e92e928426a88",
     "e8b35f3f18abe95dd936fe64ebf0fbcd059ef7561970f2dc672f466ea11ff502",
     "530ed7457f6cc13a66726b7f452fdd54e6caa23a0a735799021b7815796c6cb1",
     "530ed7457f6cc13a66726b7f452fdd54e6caa23a0a735799021b7815796c6cb1",
     0x2F0ACDC5UL, 0xB7789DC5UL, 0xB7789DC5UL,
     {0, 581632, 32768, 0, 0, 0, 0, 0}},
    {"PATCH_B", "PTLW_RIGHT_EDGE_BLUE_HOLD_A",
     "bf43684306dfae75fca05e8314a201e99e0ac441fa918114ec9120117470f009",
     "4398a1eac0bd14514658db12d9418dee779961eec007c54c7c6d8a42cedf5c9d",
     "ba5788927353d18490d16124461f84988e72681e4b8e9107b1aaa6c6298b2fca",
     "20cf7f189f13f05bb7456efe61caccc3b525fdb9002e172eabe8591b649ecabb",
     "20cf7f189f13f05bb7456efe61caccc3b525fdb9002e172eabe8591b649ecabb",
     0x0E394DC5UL, 0xEA2B3DC5UL, 0xEA2B3DC5UL,
     {0, 548864, 32768, 0, 0, 32768, 0, 0}},
    {"PATCH_C", "PTLW_LOWER_RED_HOLD_AB",
     "8a13a4fc3a06b11e23bbfb71652d3975e0b3df0c203f3688821fe33765214a4e",
     "4bf1f7000a51359cff282283e721766f7ecc9f79379cff5af809e3cca34676a0",
     "1358068272f11ca91a75c60eab2785ebfb1199f4b33db8ae715383324135c0de",
     "be2ee4c0776bda744d35b3934f5949e73624cdb8e56b9fa3e6cb9811244a8cf6",
     "be2ee4c0776bda744d35b3934f5949e73624cdb8e56b9fa3e6cb9811244a8cf6",
     0x1C410DC5UL, 0x277D31C5UL, 0x277D31C5UL,
     {0, 512000, 32768, 36864, 0, 32768, 0, 0}},
    {"WHITE_RECOVERY", "FACTORY_OTP_FULL_WHITE_RECOVERY",
     "eec52c0c4e80e5a367401c3d5b5202729336ede63fcb4d44859a3ce239b133dc",
     "4011be4a05ca71422d4e34443a2f47d3e4239f12697fe7352e8f38f1585e43f2",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};
#elif MF1750_PARTIAL_HOLD_VARIANT == 2
static constexpr const char *kVariantKey = "DUAL_CS_SPLIT";
static constexpr const char *kVariantDescription =
    "matched windows with different fixed codes on CS1 and CS2";
static constexpr const char *kContractId =
    "525efeb7ad70e9f9d502dc13feaa94f3bbf857504dd3e7b4d7c2a88ca3e30453";
static constexpr const char *kBuildTag =
    "MF1750_EC5_PARTIAL_HOLD_CS_SPLIT_V1_2026-08-22";
static constexpr const char *kTestId = "EC5-PARTIAL-HOLD-CS-SPLIT-V1";
static constexpr const char *kCampaignId = "EC5_PARTIAL_HOLD_CS_SPLIT_V1";
static constexpr const char *kNvsNamespace = "phold_split_v1";
static constexpr Window kWindows[3] = {
    {64, 64, 160, 128, 3, 5},
    {288, 236, 160, 128, 2, 6},
    {112, 408, 288, 128, 0, 3},
};
static constexpr ActionIdentity kActions[kActionCount] = {
    {"WHITE_BASELINE", "FACTORY_OTP_FULL_WHITE",
     "00b9916f0a67261a1fa968b2c41769b101adc738bab068be096555bf6be8172b",
     "44ea0c3f38dba94912d873257f0a6f6cd9da7ec020d7c8d87a1797ce91f535e3",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"PATCH_A", "PTLW_CS1_RED_CS2_BLUE",
     "6165523dc1a49761846becfd852d49c347f4c22687e7cec75c0de09ff6949bb2",
     "8f938de1a1da4403ffb8f723d7afdbeec8fd94345e3fd64fce51b64e8dca8042",
     "d7b7bf739b44d86707cbad66bddb3cfeffb8cae3420e33e9e4a389678f0765a9",
     "9ab3c7ff141c4c6cb41ce8b1478a33c5ccb01af716f11b99c28f0cd08513f705",
     "56c9f83e25f3b239deafb1f836a9d3ccb3479424101d3bed1cf17a843c184111",
     0x3AF0CDC5UL, 0xA75625C5UL, 0xBCEEE5C5UL,
     {0, 573440, 0, 20480, 0, 20480, 0, 0}},
    {"PATCH_B", "PTLW_CS1_YELLOW_CS2_GREEN_HOLD_A",
     "9584cbf58625b6a829936758d7d91302d67160d9855e1e18a9d22177d902ca87",
     "7504a526a0b14dd995724f1d56160c84c0cdb800d2e0545d3fcf3c5d55b87c5c",
     "1e5e56093b0270174d6749e4953690d4ea66d92093522a4b1734fda8ab549b94",
     "ff78e88412a9ac7c11dafb87fbd6858dd8ebeba10e5b83086489d3112a7ab858",
     "f2119d72aeece67602a1c4a7ded53f2b88b31c910d4245a4bacb4060e268021e",
     0x209FDDC5UL, 0xF50F9DC5UL, 0xFB973DC5UL,
     {0, 532480, 20480, 20480, 0, 20480, 20480, 0}},
    {"PATCH_C", "PTLW_CS1_BLACK_CS2_RED_HOLD_AB",
     "bd1c2938ed7a2bc30cd0f376dd7e2234920ab180f07b4c61b7f4a878cbc87002",
     "448d3ac6b120a6d896f55ec869d9ce21eff3252e656695f9818121e23da7e581",
     "658a8b595ef7ae0f4d9d4de135779bf34162fc311ddd08034753832c9edef82f",
     "f7b586904e3678145aa47e4232587c913139cef0102d6d8e9276fc80c35cbad3",
     "fe1d303f8b6f63459f8dce9a98ae0ffaf1cfc2380d4834dd9994234f600e910e",
     0xA7DAD5C5UL, 0x29533DC5UL, 0x531DC5C5UL,
     {36864, 458752, 20480, 57344, 0, 20480, 20480, 0}},
    {"WHITE_RECOVERY", "FACTORY_OTP_FULL_WHITE_RECOVERY",
     "d229fdecac4ca839b05110d75779e807dd1c0de0139c13322b6b21a70181df4f",
     "965bf7d413e182ac099e42840020b2410ab1d83a1b504357e2c33faf281d5968",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
    {0, 614400, 0, 0, 0, 0, 0, 0}},
};
#elif MF1750_PARTIAL_HOLD_VARIANT == 3
static constexpr const char *kVariantKey = "ACCUMULATE_VMIRROR";
static constexpr const char *kVariantDescription =
    "CS1 original windows and CS2 vertically mirrored windows";
static constexpr const char *kContractId =
    "398356c38e8ef0c0c95b40be9120578b2101c4a955145ce460d71b346de3d93f";
static constexpr const char *kBuildTag =
    "MF1750_EC5_PARTIAL_HOLD_ACC_VMIRROR_V1_2026-08-22";
static constexpr const char *kTestId =
    "EC5-PARTIAL-HOLD-ACC-VMIRROR-V1";
static constexpr const char *kCampaignId =
    "EC5_PARTIAL_HOLD_ACC_VMIRROR_V1";
static constexpr const char *kNvsNamespace = "phold_vmir_v1";
static constexpr Window kWindows[3] = {
    {48, 96, 160, 144, 3, 3},
    {304, 336, 160, 144, 5, 5},
    {80, 128, 96, 80, 6, 6},
};
static constexpr ActionIdentity kActions[kActionCount] = {
    {"WHITE_BASELINE", "FACTORY_OTP_FULL_WHITE",
     "c4f6f1088a74d39c249b5a377f1984c9fde427c95770f207fb141a65c268c3d4",
     "82aa03ba6b84d7b9c6809bac7ad1a9edc5b95ae52a1f525250c8e988ffba14e5",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"PATCH_A", "PTLW_RED_A_CS2_VMIRROR",
     "5929d8cc54bd33c2f601561937aaabef469a4cf479e5b66be5544e49cdc3efc4",
     "3a02cbe9efdb1fbdfeca84db96cd1c299e4af9927531c061c8dbd6ea5c570e9c",
     "a9d52eed806dff304aea85d0d7beec20826d986231f93b2e589855113b6f2ec5",
     "60ea54172ebc484db9d36faeb87bcdf2fa1e4ebde7879ab3e792f850aef265aa",
     "60ea54172ebc484db9d36faeb87bcdf2fa1e4ebde7879ab3e792f850aef265aa",
     0xE5A175C5UL, 0x45E756C5UL, 0x45E756C5UL,
     {0, 568320, 0, 46080, 0, 0, 0, 0}},
    {"PATCH_B", "PTLW_BLUE_B_CS2_VMIRROR_HOLD_A",
     "0f76aaba3bee80e0a011aed5d469df9c47ca6d7845ee107302233e56969c0300",
     "e752b23d05d7fed3b12c9dcaa83b815eae2a9f11dbe26514b7d99b62350a4ef5",
     "56c7ff656bffb3b70de6420e4990a6d7d8f726d9a0307c99db2dde7f9081c2c0",
     "48992a1d5b47a8d8c3e78e62ee08da4506dc09a28c8d4713a6de55b51367de84",
     "48992a1d5b47a8d8c3e78e62ee08da4506dc09a28c8d4713a6de55b51367de84",
     0xD6A0CDC5UL, 0x9A232EC5UL, 0x9A232EC5UL,
     {0, 522240, 0, 46080, 0, 46080, 0, 0}},
    {"PATCH_C", "PTLW_GREEN_C_CS2_VMIRROR_HOLD_AB",
     "e84de32ee2ab711a686743c7ab400e8460e23fe275bb7fd3908d451119a36d64",
     "e1e40932520e1c98b369715a29cea501dcb93eb7195380cb3f06cb93f378bea2",
     "a28912d108d821e947423b57112d913a651dad878d5208853612ebee5dc37dee",
     "b83e2e4addf1e5e63473804579942f23828c7ae1a1251cd2b81e3588efc4551c",
     "b83e2e4addf1e5e63473804579942f23828c7ae1a1251cd2b81e3588efc4551c",
     0xBFCF2FC5UL, 0x211299C5UL, 0x211299C5UL,
     {0, 522240, 0, 30720, 0, 46080, 15360, 0}},
    {"WHITE_RECOVERY", "FACTORY_OTP_FULL_WHITE_RECOVERY",
     "cbdae0c960d48fe764bc86c946dda9438141e6a9d9674b58b94dae1d01b777e7",
     "a32211f0eaac81653d3fba27ee99b2cef42f049f718be163deba5b60f30b8b56",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};
#elif MF1750_PARTIAL_HOLD_VARIANT == 4
static constexpr const char *kVariantKey = "ACCUMULATE_SYMMETRIC_V2";
static constexpr const char *kVariantDescription =
    "matched CS1/CS2 windows with separate 0x83 programming";
static constexpr const char *kContractId =
    "38f3211bfc2d10b544423968a11328f4e6f4a5e54ce7798db4b53f66df0710f5";
static constexpr const char *kBuildTag =
    "MF1750_EC5_PARTIAL_HOLD_ACC_SYMMETRIC_V2_2026-08-22";
static constexpr const char *kTestId =
    "EC5-PARTIAL-HOLD-ACC-SYMMETRIC-V2";
static constexpr const char *kCampaignId =
    "EC5_PARTIAL_HOLD_ACC_SYMMETRIC_V2";
static constexpr const char *kNvsNamespace = "phold_sym_v2";
static constexpr Window kWindows[3] = {
    {48, 96, 160, 144, 3, 3},
    {304, 336, 160, 144, 5, 5},
    {80, 128, 96, 80, 6, 6},
};
static constexpr ActionIdentity kActions[kActionCount] = {
    {"WHITE_BASELINE", "FACTORY_OTP_FULL_WHITE",
     "62f536336ab69553d7149de6061d854183421021a37522fc5872e82c7a6a6ab4",
     "3a285fac71eb7944be1600c92a54fee26b4485ee3e947c3ac7ec51183a9c929f",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"PATCH_A", "PTLW_RED_A_SYMMETRIC_SEPARATE_CS",
     "8e8ad1aba70b86cbc3b414c80272174444ba24e9299865ec06ef7437d786e70b",
     "beb58e8ae31ee17a534e779f9bca1dba88a9aa7f3de8d8edb6e231e5909f9f8e",
     "5c49fba44abc36aca284b691a0ca0fc78f4fd8bf0169dd856307d5f447d6a8a7",
     "60ea54172ebc484db9d36faeb87bcdf2fa1e4ebde7879ab3e792f850aef265aa",
     "60ea54172ebc484db9d36faeb87bcdf2fa1e4ebde7879ab3e792f850aef265aa",
     0xFAA175C5UL, 0x45E756C5UL, 0x45E756C5UL,
     {0, 568320, 0, 46080, 0, 0, 0, 0}},
    {"PATCH_B", "PTLW_BLUE_B_SYMMETRIC_SEPARATE_CS_HOLD_A",
     "d239e3251d8f3b6826a44d93222cb039feeb8be0e1683e9b6d0c0b64ae07a9d4",
     "79c3d8cd804712f3be1fcb1eb2135b8ef8d638f3866310faa5162a0d4650aeaa",
     "9c1c095d7f627264d6083718c409d2a4aa2b2bb98761dd6b2e92a2efa8fd6a55",
     "48992a1d5b47a8d8c3e78e62ee08da4506dc09a28c8d4713a6de55b51367de84",
     "48992a1d5b47a8d8c3e78e62ee08da4506dc09a28c8d4713a6de55b51367de84",
     0x0280CDC5UL, 0x9A232EC5UL, 0x9A232EC5UL,
     {0, 522240, 0, 46080, 0, 46080, 0, 0}},
    {"PATCH_C", "PTLW_GREEN_C_SYMMETRIC_SEPARATE_CS_HOLD_AB",
     "b97e4d641b1e7e2e246f95d722080ccfe7eaf5572623bbf1ac60db5bb824230c",
     "e64f924f73d5132905c08c8dadd2f94b79061c54cc0f10f6c57708e9a591d058",
     "aa6a03e87567f6c38374bfac1252ae29e5be972bac846492c62a45ef417be672",
     "b83e2e4addf1e5e63473804579942f23828c7ae1a1251cd2b81e3588efc4551c",
     "b83e2e4addf1e5e63473804579942f23828c7ae1a1251cd2b81e3588efc4551c",
     0x530F47C5UL, 0x211299C5UL, 0x211299C5UL,
     {0, 522240, 0, 30720, 0, 46080, 15360, 0}},
    {"WHITE_RECOVERY", "FACTORY_OTP_FULL_WHITE_RECOVERY",
     "008268d5dda61daac344a80bcc72a3b311a98e871f52ce66c81710f4108cce54",
     "03d6c4dbdfb2b712c52f5de25ae7d8f96bf216ea5b58867059676b49f24f904c",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};
#elif MF1750_PARTIAL_HOLD_VARIANT == 5
static constexpr const char *kVariantKey =
    "ACCUMULATE_SYMMETRIC_Y_INCLUSIVE";
static constexpr const char *kVariantDescription =
    "symmetric separate-CS control with y_end=y+h-1";
static constexpr const char *kContractId =
    "7ee2453859011f041c1bc28ab5e744761354b77d100338c76a7d2f4c78fbe532";
static constexpr const char *kBuildTag =
    "MF1750_EC5_PARTIAL_HOLD_ACC_SYMMETRIC_Y_INCLUSIVE_V1_2026-08-22";
static constexpr const char *kTestId =
    "EC5-PARTIAL-HOLD-ACC-SYMMETRIC-Y-INCLUSIVE-V1";
static constexpr const char *kCampaignId =
    "EC5_PARTIAL_HOLD_ACC_SYMMETRIC_Y_INCLUSIVE_V1";
static constexpr const char *kNvsNamespace = "phold_yinc_v1";
static constexpr Window kWindows[3] = {
    {48, 96, 160, 144, 3, 3},
    {304, 336, 160, 144, 5, 5},
    {80, 128, 96, 80, 6, 6},
};
static constexpr ActionIdentity kActions[kActionCount] = {
    {"WHITE_BASELINE", "FACTORY_OTP_FULL_WHITE",
     "bb8d46bacbe1a94b253e3a9707695b5eca5d06efb7bd1f092f1b196c4cff6adc",
     "2812a676af67620fb4aa9acf4cecc3d5165636b84873acfba63b800cd793d96f",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"PATCH_A", "PTLW_RED_A_SYMMETRIC_Y_INCLUSIVE",
     "1f37207b3923c5960e496eeb61b43a1e32071f2810c146abec2bc623b4734987",
     "5ff8b2ef2cf02759ed0a51507a86eeb52c0b8cc8a6f92d8b17e01fb062927ce0",
     "5c49fba44abc36aca284b691a0ca0fc78f4fd8bf0169dd856307d5f447d6a8a7",
     "60ea54172ebc484db9d36faeb87bcdf2fa1e4ebde7879ab3e792f850aef265aa",
     "60ea54172ebc484db9d36faeb87bcdf2fa1e4ebde7879ab3e792f850aef265aa",
     0xFAA175C5UL, 0x45E756C5UL, 0x45E756C5UL,
     {0, 568320, 0, 46080, 0, 0, 0, 0}},
    {"PATCH_B", "PTLW_BLUE2_B_SYMMETRIC_Y_INCLUSIVE_HOLD_A",
     "24550feb75051f2cc931e83d1542c41d82cf16491d515f0165c58137f7b9ae36",
     "c183d9384952b9068d5fc61d1663fc35e44351d5d5b0cf5f74ee00ce9a227ca8",
     "9c1c095d7f627264d6083718c409d2a4aa2b2bb98761dd6b2e92a2efa8fd6a55",
     "48992a1d5b47a8d8c3e78e62ee08da4506dc09a28c8d4713a6de55b51367de84",
     "48992a1d5b47a8d8c3e78e62ee08da4506dc09a28c8d4713a6de55b51367de84",
     0x0280CDC5UL, 0x9A232EC5UL, 0x9A232EC5UL,
     {0, 522240, 0, 46080, 0, 46080, 0, 0}},
    {"PATCH_C", "PTLW_GREEN_C_SYMMETRIC_Y_INCLUSIVE_HOLD_AB",
     "c98d8bc92345d0e913fd3627144a667315f16c9715527dd26ea06b4d6c6781a5",
     "da0a8e62bcd4b117ad8a4d057fb34b945ce08040ae1af3b463f95e67de15d08f",
     "aa6a03e87567f6c38374bfac1252ae29e5be972bac846492c62a45ef417be672",
     "b83e2e4addf1e5e63473804579942f23828c7ae1a1251cd2b81e3588efc4551c",
     "b83e2e4addf1e5e63473804579942f23828c7ae1a1251cd2b81e3588efc4551c",
     0x530F47C5UL, 0x211299C5UL, 0x211299C5UL,
     {0, 522240, 0, 30720, 0, 46080, 15360, 0}},
    {"WHITE_RECOVERY", "FACTORY_OTP_FULL_WHITE_RECOVERY",
     "3e5292b650cf749b8b8bd6a63c68838d5b2fa3b36b3508af8fe424da4a8473c6",
     "099fb943080e19b1c1252041903f1fc79c43d53fa1ce381744adb8877387d7a8",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};
#elif MF1750_PARTIAL_HOLD_VARIANT == 6
static constexpr const char *kVariantKey = "ACCUMULATE_SYMMETRIC_BLUE1";
static constexpr const char *kVariantDescription =
    "symmetric separate-CS control with PATCH_B code4 Blue-1";
static constexpr const char *kContractId =
    "fea00a484fe5cb13974c6d9a58bfa088db6c1319cd3c1e897d908a5f8943c295";
static constexpr const char *kBuildTag =
    "MF1750_EC5_PARTIAL_HOLD_ACC_SYMMETRIC_BLUE1_V1_2026-08-22";
static constexpr const char *kTestId =
    "EC5-PARTIAL-HOLD-ACC-SYMMETRIC-BLUE1-V1";
static constexpr const char *kCampaignId =
    "EC5_PARTIAL_HOLD_ACC_SYMMETRIC_BLUE1_V1";
static constexpr const char *kNvsNamespace = "phold_b1_v1";
static constexpr Window kWindows[3] = {
    {48, 96, 160, 144, 3, 3},
    {304, 336, 160, 144, 4, 4},
    {80, 128, 96, 80, 6, 6},
};
static constexpr ActionIdentity kActions[kActionCount] = {
    {"WHITE_BASELINE", "FACTORY_OTP_FULL_WHITE",
     "f5deebb30d5097051799b1c0e92ca03661b7bb93ab04800124d177d6bd55ec0a",
     "025e51dbbede0e39e30993a0678b930f3e2752ad52f4e4df8e497d58c1623302",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"PATCH_A", "PTLW_RED_A_SYMMETRIC_BLUE1_CONTROL",
     "2cb4296bfe85e424e083a34785d77965b3980f41ad442050777feb5d00f6f940",
     "9c26a4a79f40cca4b14ae36824de863cbadf06babd82415f102a489973dc1417",
     "5c49fba44abc36aca284b691a0ca0fc78f4fd8bf0169dd856307d5f447d6a8a7",
     "60ea54172ebc484db9d36faeb87bcdf2fa1e4ebde7879ab3e792f850aef265aa",
     "60ea54172ebc484db9d36faeb87bcdf2fa1e4ebde7879ab3e792f850aef265aa",
     0xFAA175C5UL, 0x45E756C5UL, 0x45E756C5UL,
     {0, 568320, 0, 46080, 0, 0, 0, 0}},
    {"PATCH_B", "PTLW_BLUE1_B_SYMMETRIC_HOLD_A",
     "4681e6d74768befe4257653ad3e5002993d04db8aa8a6f5d88478637ef196891",
     "1a99a5051131e28a0da71473c7ed32483578f3462315172bc0a67b10ababdcfd",
     "8154148554358777f54ceb50854c59d1653ff4c47e86c4ac3219bb68cb25edf7",
     "437e69ad80ca440a0c4255806470a64b1d728724750ed9e061f1d9315b6114d6",
     "437e69ad80ca440a0c4255806470a64b1d728724750ed9e061f1d9315b6114d6",
     0x6D5A63C5UL, 0x57BAB5C5UL, 0x57BAB5C5UL,
     {0, 522240, 0, 46080, 46080, 0, 0, 0}},
    {"PATCH_C", "PTLW_GREEN_C_SYMMETRIC_HOLD_BLUE1",
     "9edee88c1ad3896a632f2329e695a48b9ceb5a3700b10c42de2a218742b9a6be",
     "b9ccd16109ee65f718e45c007cdf39195b76858b9858fc95aafb2f3c299f9456",
     "6851309fe86399fe6be01c63b108cd08bfd7554d694476417d2d360eb73d4eca",
     "b83e2e4addf1e5e63473804579942f23828c7ae1a1251cd2b81e3588efc4551c",
     "b83e2e4addf1e5e63473804579942f23828c7ae1a1251cd2b81e3588efc4551c",
     0xBDE8DDC5UL, 0x211299C5UL, 0x211299C5UL,
     {0, 522240, 0, 30720, 46080, 0, 15360, 0}},
    {"WHITE_RECOVERY", "FACTORY_OTP_FULL_WHITE_RECOVERY",
     "215248380c3ed90f3bf626831115976e7d1d38761d396b05585ab624f625e44e",
     "26f67ece80745109f928d0c76690fc88802cb0610cd0621904bca059a8767856",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};
#else
static constexpr const char *kVariantKey =
    "ACCUMULATE_SYMMETRIC_Y_INCLUSIVE_BLUE1";
static constexpr const char *kVariantDescription =
    "y-inclusive symmetric control with PATCH_B code4 Blue-1";
static constexpr const char *kContractId =
    "233b47ea8dc67c7b04d902aaddc7f8e460110eab09cb6b54d7484f63cabc09a0";
static constexpr const char *kBuildTag =
    "MF1750_EC5_PARTIAL_HOLD_ACC_SYMMETRIC_Y_INCLUSIVE_BLUE1_V1_2026-08-22";
static constexpr const char *kTestId =
    "EC5-PARTIAL-HOLD-ACC-SYMMETRIC-Y-INCLUSIVE-BLUE1-V1";
static constexpr const char *kCampaignId =
    "EC5_PARTIAL_HOLD_ACC_SYMMETRIC_Y_INCLUSIVE_BLUE1_V1";
static constexpr const char *kNvsNamespace = "ph_yinc_b1_v1";
static constexpr Window kWindows[3] = {
    {48, 96, 160, 144, 3, 3},
    {304, 336, 160, 144, 4, 4},
    {80, 128, 96, 80, 6, 6},
};
static constexpr ActionIdentity kActions[kActionCount] = {
    {"WHITE_BASELINE", "FACTORY_OTP_FULL_WHITE",
     "d13603038cf8cc05ee11f5079e275413b912d20a92649aa5c7ca9dc2da1210f8",
     "07bbf3543fb8ce2eec143bc45ab71ef3516cda5df7914f503745ea05a48e6a21",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"PATCH_A", "PTLW_RED_A_SYMMETRIC_Y_INCLUSIVE_BLUE1_CONTROL",
     "862927ebeba8a3fb1a8eb38206cad4ac3f2bab0b132b934f39bf174a78d2837f",
     "bdd31a955b4933977387c54f52998555d6a8294896a939dcc856982f46151a94",
     "5c49fba44abc36aca284b691a0ca0fc78f4fd8bf0169dd856307d5f447d6a8a7",
     "60ea54172ebc484db9d36faeb87bcdf2fa1e4ebde7879ab3e792f850aef265aa",
     "60ea54172ebc484db9d36faeb87bcdf2fa1e4ebde7879ab3e792f850aef265aa",
     0xFAA175C5UL, 0x45E756C5UL, 0x45E756C5UL,
     {0, 568320, 0, 46080, 0, 0, 0, 0}},
    {"PATCH_B", "PTLW_BLUE1_B_SYMMETRIC_Y_INCLUSIVE_HOLD_A",
     "a259374b530591b2748b958602acedd43ab1301d1e2caa26900e2485b43ea1c4",
     "96186fcf9018977e819c87c2f182c17279e51c00b81c7168bd7c73bfa37e1b3e",
     "8154148554358777f54ceb50854c59d1653ff4c47e86c4ac3219bb68cb25edf7",
     "437e69ad80ca440a0c4255806470a64b1d728724750ed9e061f1d9315b6114d6",
     "437e69ad80ca440a0c4255806470a64b1d728724750ed9e061f1d9315b6114d6",
     0x6D5A63C5UL, 0x57BAB5C5UL, 0x57BAB5C5UL,
     {0, 522240, 0, 46080, 46080, 0, 0, 0}},
    {"PATCH_C", "PTLW_GREEN_C_SYMMETRIC_Y_INCLUSIVE_HOLD_BLUE1",
     "8de74db06796610834cd95841c5b661300171863eef11731d1a475c085dca0e6",
     "2e3857e2c32b8f925e8e02592efc227c6d79d61e42ea2f2eb67bb4c674aa3129",
     "6851309fe86399fe6be01c63b108cd08bfd7554d694476417d2d360eb73d4eca",
     "b83e2e4addf1e5e63473804579942f23828c7ae1a1251cd2b81e3588efc4551c",
     "b83e2e4addf1e5e63473804579942f23828c7ae1a1251cd2b81e3588efc4551c",
     0xBDE8DDC5UL, 0x211299C5UL, 0x211299C5UL,
     {0, 522240, 0, 30720, 46080, 0, 15360, 0}},
    {"WHITE_RECOVERY", "FACTORY_OTP_FULL_WHITE_RECOVERY",
     "01a07d04955700e5bd39e9185b92ae540daa5ba01501d942bf7b236c01ebcc7d",
     "9322704af487c78db3d503208cbc868d9db13490b87de554e7556791d4054e21",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};
#endif

static_assert(sizeof(kWindows) / sizeof(kWindows[0]) == 3,
              "partial HOLD requires exactly three fixed windows");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "partial HOLD requires exactly five actions");

}  // namespace mf1750_partial_hold
