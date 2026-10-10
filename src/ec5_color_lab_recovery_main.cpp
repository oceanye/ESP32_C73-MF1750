#include <Arduino.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <esp_system.h>

#include <cstdio>
#include <cstring>

#include "epd_config.h"
#include "epd_driver.h"

// Isolated single-flash EC5 colour-lab recovery campaign. Every visible action is
// independently armed and executed. There is no startup refresh, raw frame
// ingress, automatic chaining, retry, recovery, or NVS clear endpoint. The old
// mf1750_ec5cl/cursor fault key is deliberately ignored and never cleared.
#if MF1750_ENABLE_COLOR_LAB != 1
#error "EC5 COLOR_LAB requires MF1750_ENABLE_COLOR_LAB=1"
#endif

#if MF1750_ENABLE_EIGHTCODE_ATLAS != 1
#error "EC5 COLOR_LAB requires MF1750_ENABLE_EIGHTCODE_ATLAS=1"
#endif

#ifndef EPD_ENABLE_TEST_PATTERN
#error "EC5 COLOR_LAB requires explicit EPD_ENABLE_TEST_PATTERN=0"
#endif

#if EPD_ENABLE_TEST_PATTERN != 0
#error "EC5 COLOR_LAB must never refresh during startup"
#endif

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600,
              "EC5 COLOR_LAB is frozen for the 1024x600 panel");
static_assert(EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "EC5 COLOR_LAB requires the frozen 4bpp cascade geometry");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "EC5 COLOR_LAB mapping differs from MAP_ORIENT_V1");

namespace {

WebServer server(80);
Preferences cursorStore;

static constexpr const char *kClassification =
    "TECHNICAL_RECOVERY_EXPERIMENT_NO_PHYSICAL_COLOUR_CLAIM";
static constexpr const char *kIdentityRevision = "color-lab-recovery-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_COLOR_LAB_RECOVERY_DEVICE_V1";
static constexpr const char *kLayoutId =
    "EC5_COLOR_LAB_RECOVERY_COMPOSED_FIXED_FRAMES_V1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_COLOR_LAB_RECOVERY_V1_2026-08-10";
static constexpr const char *kTestId = "EC5-COLOR-LAB-RECOVERY-V1";
static constexpr const char *kCampaignId =
    "EC5_COLOR_LAB_RECOVERY_CAMPAIGN_V1";
static constexpr const char *kContractId =
    "52eb05232f6ad2fe001c6fe0e6c96864c69a9a058a4626e84eb5cbe1377d4736";

static constexpr const char *kNvsNamespace = "mf1750_ec5clr";
static constexpr const char *kNvsKey = "cursor_r1";

static constexpr const char *kVersionRoute =
    "/api/ec5/color-lab/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/color-lab/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/color-lab/status";
static constexpr const char *kReportRoute =
    "/api/ec5/color-lab/report";
static constexpr const char *kArmRoute = "/api/ec5/color-lab/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/color-lab/execute";

static constexpr const char *kBuildHeader = "X-EC5-Build-Tag";
static constexpr const char *kTestHeader = "X-EC5-Test-Id";
static constexpr const char *kCampaignHeader = "X-EC5-Campaign-Id";
static constexpr const char *kActionHeader = "X-EC5-Action-Id";
static constexpr const char *kOrdinalHeader = "X-EC5-Ordinal";
static constexpr const char *kDescriptorHeader = "X-EC5-Descriptor-Id";
static constexpr const char *kBootNonceHeader = "X-EC5-Boot-Nonce";
static constexpr const char *kArmNonceHeader = "X-EC5-Arm-Nonce";
static constexpr const char *kIntentHeader = "X-EC5-Intent";
static constexpr const char *kArmIntent =
    "ARM_ONE_FIXED_COLOR_LAB_RECOVERY_ACTION_NOT_HARDWARE_AUTHORIZATION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ONE_FIXED_COLOR_LAB_RECOVERY_ACTION_NOT_HARDWARE_AUTHORIZATION";

static constexpr uint8_t kPhaseReady = 0;
static constexpr uint8_t kPhaseArmed = 1;
static constexpr uint8_t kPhaseConsumed = 2;
static constexpr uint8_t kPhaseFault = 3;
static constexpr uint8_t kActionCount = 23;
static constexpr uint8_t kTerminalOrdinal = kActionCount + 1;

struct ActionDescriptor {
  uint8_t ordinal;
  EpdColorLabRole driverRole;
  const char *role;
  uint8_t round;
  const char *branch;
  const char *descriptorId;
  const char *actionId;
  const char *priorActionId;
  const char *frameSha256;
  const char *cs1DtmSha256;
  const char *cs2DtmSha256;
};

static constexpr const char *kWhiteFrameSha256 =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr const char *kWhiteDtmSha256 =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";
static constexpr const char *kU07IsolatedFrameSha256 =
    "d9d43888c68b483776bb43a53cc1084b8549d00d9ff70ef2f1227fafe0ac7b3e";
static constexpr const char *kU07IsolatedDtmSha256 =
    "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac";
static constexpr const char *kAtlasFrameSha256 =
    "77454fe933f79b301ecb55b2a065276e0f4fe122bf8416746f71f9b92e90637b";
static constexpr const char *kAtlasCs1DtmSha256 =
    "85cd5683ae2d9c5bf9e97bea539a905cdf244983befaeba7e5321aa73ed774f7";
static constexpr const char *kAtlasCs2DtmSha256 =
    "cfb5bba82a9421e4c3a13ed10731105d78852a05238ca52ddf3bd9cdd099b943";
static constexpr const char *kPrimerFrameSha256 =
    "94ee82ae66fe8372e8c1d977a158dc60d55c36da86fc44f8b2a9a01c6d47ab0e";
static constexpr const char *kPrimerDtmSha256 =
    "f5bb17a5726f851da2bf322ffea8f0ea791f70788184ada4261b89aa43dc39af";
static constexpr const char *kU04TargetFrameSha256 =
    "81b0ed1b715551ddb2546d4f123c5c3d479bc8802ff9d2570e38d9b57b4645e6";
static constexpr const char *kU04TargetDtmSha256 =
    "c4efd83606b72c49b7c0d67865e4df98ef31e5d40f071299558e10c5a212dd0f";
static constexpr const char *kU07TargetFrameSha256 =
    "149ba0f5c3fd779d6870f655b53d726d6d1297e016331de4d394e411410e0e21";
static constexpr const char *kU07TargetDtmSha256 =
    "139a0aa919d78a1aa572db49a7c90fe3a4f29476ab4d80ba3bb0f439f0191b3d";

#define WHITE_ACTION(ORD, ROUND, BRANCH, DESC, ACTION, PRIOR)                \
  {ORD, EpdColorLabRole::White, "WHITE", ROUND, BRANCH, DESC, ACTION, PRIOR, \
   kWhiteFrameSha256, kWhiteDtmSha256, kWhiteDtmSha256}
#define PRIMER_ACTION(ORD, ENUM_ROLE, ROLE, ROUND, DESC, ACTION, PRIOR)       \
  {ORD, ENUM_ROLE, ROLE, ROUND, "U0" #ORD "_SIXSTATE", DESC, ACTION, PRIOR, \
   kPrimerFrameSha256, kPrimerDtmSha256, kPrimerDtmSha256}

// The branch string is explicit below; macros are used only to keep repeated
// frozen frame identities visibly identical. No action identity is generated
// at runtime.
static constexpr ActionDescriptor kActions[] = {
    WHITE_ACTION(1, 0, "COMPARE_AFTER_WHITE",
                 "9fccc2cca111e81af285dc3e7dc94af18f2addd5b5c814e7f14c8003b0f08b31",
                 "04ace39dc527f7fa4d6141f2ccd128a5b97c2a6832e526e98d1d24573795aa95",
                 nullptr),
    {2, EpdColorLabRole::U07Isolated, "U07_ISOLATED", 0, "ISOLATED_U07",
     "e0d8ba9aa48fd866d6be7ea27efd53527c654f09d7767167b3c55a79bfeea774",
     "0e83b3d6255ca8eea91d80be36d7bdd9a253c601d510f08ce9166e5a3eeee4fd",
     "04ace39dc527f7fa4d6141f2ccd128a5b97c2a6832e526e98d1d24573795aa95",
     kU07IsolatedFrameSha256, kU07IsolatedDtmSha256,
     kU07IsolatedDtmSha256},
    WHITE_ACTION(3, 0, "AFTER_ISOLATED_U07_WHITE",
                 "9e3f2d811f5640ba2746e597c652f4ba06cd27204a7b99a6b19384f2bf7c6e4c",
                 "b5fec9ff9ccff73d4959687215122049da9e309711901bea5946782b866f4ce3",
                 "0e83b3d6255ca8eea91d80be36d7bdd9a253c601d510f08ce9166e5a3eeee4fd"),
    {4, EpdColorLabRole::Atlas, "ATLAS_0_7", 0, "BALANCED_EIGHTCODE_ATLAS",
     "4ca2064d656d26be801722250f408787dfc0f9fbae8dab3ff8849ae3a5ea1ce9",
     "4a7b6b43877640614fe9c3f56b8de5ddf7c9bd3bd7d79377049c082bfdab4033",
     "b5fec9ff9ccff73d4959687215122049da9e309711901bea5946782b866f4ce3",
     kAtlasFrameSha256, kAtlasCs1DtmSha256, kAtlasCs2DtmSha256},
    WHITE_ACTION(5, 0, "AFTER_ATLAS_WHITE",
                 "b7db9ce5219e7557a8f86813d84af1c4a2da47c25d54c81599c6313cbea18867",
                 "bacf670e67ce4739df84280b91a42c0b7566d0cadac1acc3b4a7ad86d20824cc",
                 "4a7b6b43877640614fe9c3f56b8de5ddf7c9bd3bd7d79377049c082bfdab4033"),
    {6, EpdColorLabRole::U04SixStatePrimer, "U04_SIXSTATE_PRIMER", 1,
     "U04_SIXSTATE",
     "8ce858a673a055206c83d8819217cb8628e014998f68bc3be2e31c0d527a7831",
     "6037f5392ee1001db083847342022b63e7eb8d48e63142acf683197c1cb68210",
     "bacf670e67ce4739df84280b91a42c0b7566d0cadac1acc3b4a7ad86d20824cc",
     kPrimerFrameSha256, kPrimerDtmSha256, kPrimerDtmSha256},
    {7, EpdColorLabRole::U04SixStateTarget, "U04_SIXSTATE_TARGET", 1,
     "U04_SIXSTATE",
     "7050f156ba1c4794d197c695eb2f1ad0865e7ad6dc83b21c62ee0d11d53e2547",
     "33a1f89f1bc7e397a40a7ec7cd509757ad03c2e75e7741cc019b5a1faf878cb3",
     "6037f5392ee1001db083847342022b63e7eb8d48e63142acf683197c1cb68210",
     kU04TargetFrameSha256, kU04TargetDtmSha256, kU04TargetDtmSha256},
    WHITE_ACTION(8, 1, "AFTER_U04_SIXSTATE_WHITE",
                 "2c7f7c3dc36f9257ae45161e0d505f9a42abaf71a2ffeb83f5a409f5aa21a13a",
                 "19eb6cc1dd75bec2f8175c44463669215920a294de29ef5cd9d59c789c9b63f5",
                 "33a1f89f1bc7e397a40a7ec7cd509757ad03c2e75e7741cc019b5a1faf878cb3"),
    {9, EpdColorLabRole::U07SixStatePrimer, "U07_SIXSTATE_PRIMER", 1,
     "U07_SIXSTATE",
     "98846d6a558f3efe2746cafdb68c6016520e91c6fc0819f0101f3bed1746140b",
     "a49c5247807118e8d0befe644e0369c36710c63006adecb3a7a8d45969f3a547",
     "19eb6cc1dd75bec2f8175c44463669215920a294de29ef5cd9d59c789c9b63f5",
     kPrimerFrameSha256, kPrimerDtmSha256, kPrimerDtmSha256},
    {10, EpdColorLabRole::U07SixStateTarget, "U07_SIXSTATE_TARGET", 1,
     "U07_SIXSTATE",
     "1f506229467bef703b1647cd427e25a92dc614b8d0fe486e3c284a15d047386a",
     "51c335e19a8d9a1d1061af2115f3a542ae6686b5be0d2607f648e80902d46a14",
     "a49c5247807118e8d0befe644e0369c36710c63006adecb3a7a8d45969f3a547",
     kU07TargetFrameSha256, kU07TargetDtmSha256, kU07TargetDtmSha256},
    WHITE_ACTION(11, 1, "AFTER_U07_SIXSTATE_WHITE",
                 "ae99939284a422267f5648c04a37d2eb79bc1eb59d3886bb5c1dffc9fb7b59a7",
                 "98881513368c332d8d685b4882c18e478ae160809bb98d9f5028258d7ed0e882",
                 "51c335e19a8d9a1d1061af2115f3a542ae6686b5be0d2607f648e80902d46a14"),
    {12, EpdColorLabRole::U04SixStatePrimer, "U04_SIXSTATE_PRIMER", 2,
     "U04_SIXSTATE",
     "d6c8d0941466ac7bdc0b79719186bfbad7ba9fcd0be5a06ddbb6390c1cfa804b",
     "e80a6e250d371e88874f05e5256f8a9d369079678d258565121a1be75fa477fd",
     "98881513368c332d8d685b4882c18e478ae160809bb98d9f5028258d7ed0e882",
     kPrimerFrameSha256, kPrimerDtmSha256, kPrimerDtmSha256},
    {13, EpdColorLabRole::U04SixStateTarget, "U04_SIXSTATE_TARGET", 2,
     "U04_SIXSTATE",
     "ebdcf979e0a6d78f2f1dff516c93db6ab1527378059e15ac67b56f1a7a688a61",
     "c611dcf7a815e67a484ac9f02da6e16e4d1381e31184fb8d1ddbdbbdf8d26771",
     "e80a6e250d371e88874f05e5256f8a9d369079678d258565121a1be75fa477fd",
     kU04TargetFrameSha256, kU04TargetDtmSha256, kU04TargetDtmSha256},
    WHITE_ACTION(14, 2, "AFTER_U04_SIXSTATE_WHITE",
                 "3a90ab9403c334b8f184649574b3cd2f08f33964a3ab017d1d910a7b9a579764",
                 "9813043196fa4083486f7d91cf27e4cd931f8ea4d2ec14a85e908c43d8cb1a40",
                 "c611dcf7a815e67a484ac9f02da6e16e4d1381e31184fb8d1ddbdbbdf8d26771"),
    {15, EpdColorLabRole::U07SixStatePrimer, "U07_SIXSTATE_PRIMER", 2,
     "U07_SIXSTATE",
     "6b7eff492e7ec63e95080edf2f8f0693ccf45d2e1d1adc0ac347425e3d9767aa",
     "fbd749356aed60501d025200ab7b7e4499fbcae467f2e3ef5f76a7768a194ee3",
     "9813043196fa4083486f7d91cf27e4cd931f8ea4d2ec14a85e908c43d8cb1a40",
     kPrimerFrameSha256, kPrimerDtmSha256, kPrimerDtmSha256},
    {16, EpdColorLabRole::U07SixStateTarget, "U07_SIXSTATE_TARGET", 2,
     "U07_SIXSTATE",
     "f672d1ff8424d61e929a76027f20a904f256d990605184a22d734cabc2417665",
     "ab95d58e57f6868eb31897182a326528dde69e7159626a5b927d35d553fdfb7e",
     "fbd749356aed60501d025200ab7b7e4499fbcae467f2e3ef5f76a7768a194ee3",
     kU07TargetFrameSha256, kU07TargetDtmSha256, kU07TargetDtmSha256},
    WHITE_ACTION(17, 2, "AFTER_U07_SIXSTATE_WHITE",
                 "8753e25c3b745305414d6f755c161d1fce056df927da965791f3fad44e7cfdd3",
                 "c4954aae694486fc21de10a53cfe66d0f3a7ce410acc48c4442be6521dfb6e1f",
                 "ab95d58e57f6868eb31897182a326528dde69e7159626a5b927d35d553fdfb7e"),
    {18, EpdColorLabRole::U04SixStatePrimer, "U04_SIXSTATE_PRIMER", 3,
     "U04_SIXSTATE",
     "749b64185e1efe6843e0291bfe04defb8ce8d9c85d48c1e4593af03f07eeb55c",
     "e3eba60ba0f11e384a8eeb404b33257cfe4b504d712d6b4def1548eda36ecd59",
     "c4954aae694486fc21de10a53cfe66d0f3a7ce410acc48c4442be6521dfb6e1f",
     kPrimerFrameSha256, kPrimerDtmSha256, kPrimerDtmSha256},
    {19, EpdColorLabRole::U04SixStateTarget, "U04_SIXSTATE_TARGET", 3,
     "U04_SIXSTATE",
     "bcc9f77df49cd33b59ac08e930571a5a2c3be07ca27465d994114b22f665df23",
     "d0081f34d4bc333404778c9dcaa16a8290e414deb81ba8472bebde4673235248",
     "e3eba60ba0f11e384a8eeb404b33257cfe4b504d712d6b4def1548eda36ecd59",
     kU04TargetFrameSha256, kU04TargetDtmSha256, kU04TargetDtmSha256},
    WHITE_ACTION(20, 3, "AFTER_U04_SIXSTATE_WHITE",
                 "ebd5b958f5439369a5fa9c5fd2587b79068238bfd3bdc5680daa70db8eb0f1c6",
                 "f01b6569d6b94f9225f3114a60adc6c4a7a13ebc7b865546bfec2778bb322581",
                 "d0081f34d4bc333404778c9dcaa16a8290e414deb81ba8472bebde4673235248"),
    {21, EpdColorLabRole::U07SixStatePrimer, "U07_SIXSTATE_PRIMER", 3,
     "U07_SIXSTATE",
     "d94e70aa97668186e345b28041ca69225cb6c49233cfa92ffaf800c84d21b1fb",
     "c0052b3e08bbe5432e00b4fd26e0f4ac97452a248356e71b4981b8efa16ea5cf",
     "f01b6569d6b94f9225f3114a60adc6c4a7a13ebc7b865546bfec2778bb322581",
     kPrimerFrameSha256, kPrimerDtmSha256, kPrimerDtmSha256},
    {22, EpdColorLabRole::U07SixStateTarget, "U07_SIXSTATE_TARGET", 3,
     "U07_SIXSTATE",
     "b73dc63138fe79927da2c1a1132e14f3215600cd11a33b3df07e1753ab2e9edc",
     "f2872088d77fd5ddb86c61407602dec3a506b81c64c46ccec4476f62be087a40",
     "c0052b3e08bbe5432e00b4fd26e0f4ac97452a248356e71b4981b8efa16ea5cf",
     kU07TargetFrameSha256, kU07TargetDtmSha256, kU07TargetDtmSha256},
    WHITE_ACTION(23, 3, "AFTER_U07_SIXSTATE_WHITE",
                 "d5cdde2357d14e5e6d522eb31692fa9c66546c2c91b69a0644a9fe99e3e63ba6",
                 "402bcad1424195543edd100f58c342d2b897e244d720c0c08156ca49eaf3e753",
                 "f2872088d77fd5ddb86c61407602dec3a506b81c64c46ccec4476f62be087a40"),
};

#undef PRIMER_ACTION
#undef WHITE_ACTION

static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "EC5 COLOR_LAB action table must contain exactly 23 actions");

enum class RuntimeState : uint8_t {
  BootSelfCheck,
  Ready,
  Armed,
  Queued,
  Running,
  Complete,
  FaultLocked,
};

RuntimeState state = RuntimeState::BootSelfCheck;
bool fixtureSelfCheckPassed = false;
bool gpioInitialized = false;
bool storeReady = false;
bool keyPresent = false;
bool executePending = false;
uint8_t persistentPhase = kPhaseReady;
uint8_t nextOrdinal = 1;
uint16_t cursorRaw = 1;
uint32_t bootNonceHigh = 0;
uint32_t bootNonceLow = 0;
uint32_t armNonceHigh = 0;
uint32_t armNonceLow = 0;
uint32_t armRequestCount = 0;
uint32_t executeRequestCount = 0;
uint32_t totalDriverCallCount = 0;
uint8_t driverCallCountForAction = 0;
uint32_t jobQueuedAtMs = 0;
uint32_t jobStartedAtMs = 0;
uint32_t jobFinishedAtMs = 0;
String publishedReport =
    "{\"schema_version\":3,\"valid\":false,\"error\":\"boot_self_check\"}";

const char *stateName(RuntimeState value) {
  switch (value) {
    case RuntimeState::BootSelfCheck:
      return "boot_self_check";
    case RuntimeState::Ready:
      return "ready";
    case RuntimeState::Armed:
      return "armed";
    case RuntimeState::Queued:
      return "queued";
    case RuntimeState::Running:
      return "running";
    case RuntimeState::Complete:
      return "complete";
    case RuntimeState::FaultLocked:
      return "fault_locked";
  }
  return "fault_locked";
}

const char *phaseName(uint8_t phase) {
  switch (phase) {
    case kPhaseReady:
      return "READY";
    case kPhaseArmed:
      return "ARMED";
    case kPhaseConsumed:
      return "CONSUMED";
    case kPhaseFault:
      return "FAULT";
  }
  return "INVALID";
}

String hex32(uint32_t value) {
  char output[9] = {};
  snprintf(output, sizeof(output), "%08lx",
           static_cast<unsigned long>(value));
  return String(output);
}

String bootNonce() { return hex32(bootNonceHigh) + hex32(bootNonceLow); }
String armNonce() { return hex32(armNonceHigh) + hex32(armNonceLow); }

uint16_t encodeCursor(uint8_t phase, uint8_t ordinal) {
  return static_cast<uint16_t>((static_cast<uint16_t>(phase) << 8) | ordinal);
}

bool cursorFieldsValid(uint8_t phase, uint8_t ordinal) {
  if (phase == kPhaseReady) return ordinal >= 1 && ordinal <= kTerminalOrdinal;
  return phase <= kPhaseFault && ordinal >= 1 && ordinal <= kActionCount;
}

bool refreshCursorEvidence() {
  if (!storeReady) return false;
  keyPresent = cursorStore.isKey(kNvsKey);
  cursorRaw = keyPresent ? cursorStore.getUShort(kNvsKey, 0) : encodeCursor(0, 1);
  persistentPhase = static_cast<uint8_t>((cursorRaw >> 8) & 0xFFU);
  nextOrdinal = static_cast<uint8_t>(cursorRaw & 0xFFU);
  return cursorFieldsValid(persistentPhase, nextOrdinal);
}

bool persistCursor(uint8_t phase, uint8_t ordinal) {
  if (!storeReady || !cursorFieldsValid(phase, ordinal)) return false;
  const uint16_t wanted = encodeCursor(phase, ordinal);
  if (cursorStore.putUShort(kNvsKey, wanted) != sizeof(uint16_t)) return false;
  if (!refreshCursorEvidence()) return false;
  return keyPresent && cursorRaw == wanted && persistentPhase == phase &&
         nextOrdinal == ordinal;
}

const ActionDescriptor *actionForOrdinal(uint8_t ordinal) {
  if (ordinal < 1 || ordinal > kActionCount) return nullptr;
  const ActionDescriptor &action = kActions[ordinal - 1];
  return action.ordinal == ordinal ? &action : nullptr;
}

const ActionDescriptor *currentAction() { return actionForOrdinal(nextOrdinal); }

bool requestHasBodyOrArguments() {
  if (server.args() != 0 || server.hasArg("plain")) return true;
  const String contentType = server.header("Content-Type");
  const String transferEncoding = server.header("Transfer-Encoding");
  const String contentLength = server.header("Content-Length");
  if (!contentType.isEmpty() || !transferEncoding.isEmpty()) return true;
  return !contentLength.isEmpty() && contentLength != "0";
}

bool requireReadOnlyRequest() {
  if (!requestHasBodyOrArguments()) return true;
  server.send(400, "application/json",
              "{\"error\":\"read_only_route_rejects_body_or_arguments\"}");
  return false;
}

bool exactHeader(const char *name, const String &expected) {
  return server.hasHeader(name) && server.header(name) == expected;
}

const char *validateMutationContract(const ActionDescriptor &action,
                                     const char *intent,
                                     bool requireArmNonce) {
  if (requestHasBodyOrArguments()) return "body_or_arguments_forbidden";
  if (!exactHeader(kBuildHeader, kBuildTag))
    return "build_tag_missing_or_mismatch";
  if (!exactHeader(kTestHeader, kTestId))
    return "test_id_missing_or_mismatch";
  if (!exactHeader(kCampaignHeader, kCampaignId))
    return "campaign_id_missing_or_mismatch";
  if (!exactHeader(kActionHeader, action.actionId))
    return "action_id_missing_or_mismatch";
  if (!exactHeader(kOrdinalHeader, String(action.ordinal)))
    return "ordinal_missing_or_mismatch";
  if (!exactHeader(kDescriptorHeader, action.descriptorId))
    return "descriptor_id_missing_or_mismatch";
  if (!exactHeader(kBootNonceHeader, bootNonce()))
    return "boot_nonce_missing_or_stale";
  if (!exactHeader(kIntentHeader, intent)) return "intent_missing_or_mismatch";
  if (requireArmNonce && !exactHeader(kArmNonceHeader, armNonce()))
    return "arm_nonce_missing_or_stale";
  return nullptr;
}

String nvsContractJson() {
  return String("\"nvs_contract\":{\"namespace\":\"") + kNvsNamespace +
         "\",\"key\":\"" + kNvsKey +
         "\",\"encoding\":\"uint16 high_byte_phase low_byte_next_ordinal\"," +
         "\"phases\":{\"READY\":0,\"ARMED\":1,\"CONSUMED\":2,\"FAULT\":3}," +
         "\"initial_key_present\":false,\"initial_next_ordinal\":1," +
         "\"terminal_next_ordinal\":24}";
}

String recoveryMigrationJson() {
  return "\"recovery_migration\":{"
         "\"old_nvs_namespace\":\"mf1750_ec5cl\","
         "\"old_nvs_key\":\"cursor\","
         "\"old_state_ignored_not_cleared\":true,"
         "\"global_nvs_clear\":false,"
         "\"wifi_credentials_preserved\":true}";
}

String identityJson() {
  return String("\"build_tag\":\"") + kBuildTag + "\",\"test_id\":\"" +
         kTestId + "\",\"campaign_id\":\"" + kCampaignId +
         "\",\"device_api_version\":\"" + kDeviceApiVersion +
         "\",\"identity_revision\":\"" + kIdentityRevision +
         "\",\"contract_id\":\"" + kContractId + "\"";
}

String actionJson(const ActionDescriptor &action) {
  return String("{\"ordinal\":") + String(action.ordinal) +
         ",\"descriptor_id\":\"" + action.descriptorId +
         "\",\"action_id\":\"" + action.actionId +
         "\",\"prior_static_action_id\":" +
         (action.priorActionId ? String("\"") + action.priorActionId + "\""
                               : String("null")) +
         ",\"role\":\"" + action.role + "\",\"round\":" +
         String(action.round) + ",\"branch\":\"" + action.branch +
         "\",\"frame_sha256\":\"" + action.frameSha256 +
         "\",\"cs1_dtm_sha256\":\"" + action.cs1DtmSha256 +
         "\",\"cs2_dtm_sha256\":\"" + action.cs2DtmSha256 + "\"}";
}

String versionJson() {
  refreshCursorEvidence();
  return String("{\"schema_version\":3,\"kind\":") +
         "\"mf1750-ec5-color-lab-recovery-version\"," + identityJson() +
         ",\"classification\":\"" + kClassification +
         "\",\"layout_id\":\"" + kLayoutId +
         "\",\"driver_api_version\":\"" + EPD_DRIVER_API_VERSION +
         "\",\"action_count\":23,\"automatic_execute\":false," +
         "\"automatic_chaining\":false,\"startup_refresh\":false," +
         "\"raw_frame_ingress\":false,\"dither\":false," +
         "\"retry\":false,\"recovery\":false," + nvsContractJson() + "," +
         recoveryMigrationJson() + "}";
}

String manifestJson() {
  String output = String("{\"schema_version\":3,\"kind\":") +
                  "\"mf1750-ec5-color-lab-recovery-manifest\"," + identityJson() +
                  ",\"classification\":\"" + kClassification +
                  "\",\"layout_id\":\"" + kLayoutId +
                  "\",\"action_count\":23,\"round_count\":3," +
                  "\"round_one_safe_stop_completed_ordinal\":11," +
                  "\"round_one_safe_stop_next_ordinal\":12," +
                  "\"automatic_chaining\":false,\"startup_refresh\":false," +
                  "\"raw_frame_ingress\":false,\"dither\":false," +
                  "\"retry\":false,\"recovery\":false,\"actions\":[";
  for (uint8_t index = 0; index < kActionCount; ++index) {
    if (index != 0) output += ',';
    output += actionJson(kActions[index]);
  }
  output += String("],") + nvsContractJson() + "," +
            recoveryMigrationJson() + "}";
  return output;
}

String gpioJson() {
  if (!gpioInitialized)
    return "\"gpio_initialized\":false,\"busy\":null,\"rst\":null,"
           "\"cs\":null,\"cs2\":null";
  return String("\"gpio_initialized\":true,\"busy\":") +
         String(epdReadBusy()) + ",\"rst\":" +
         String(digitalRead(EPD_PIN_RST)) + ",\"cs\":" +
         String(digitalRead(EPD_PIN_CS)) + ",\"cs2\":" +
         String(digitalRead(EPD_PIN_CS2));
}

String statusJson() {
  const bool cursorValid = refreshCursorEvidence();
  const ActionDescriptor *action = currentAction();
  // READY advertises only next_ordinal; it has no active/claimed action.
  // ARMED/CONSUMED/FAULT expose the exact action bound to the cursor.
  String current = action && persistentPhase != kPhaseReady
                       ? actionJson(*action)
                       : String("null");
  return String("{\"schema_version\":3,\"kind\":") +
         "\"mf1750-ec5-color-lab-recovery-status\"," + identityJson() +
         ",\"classification\":\"" + kClassification +
         "\",\"boot_nonce\":\"" + bootNonce() +
         "\",\"state\":\"" + stateName(state) + "\",\"phase\":" +
         String(persistentPhase) + ",\"phase_name\":\"" +
         phaseName(persistentPhase) + "\",\"cursor_raw\":" +
         String(cursorRaw) + ",\"next_ordinal\":" + String(nextOrdinal) +
         ",\"current_action\":" + current +
         ",\"campaign_complete\":" +
         (nextOrdinal == kTerminalOrdinal && persistentPhase == kPhaseReady
              ? "true"
              : "false") +
         ",\"fixture_self_check_passed\":" +
         (fixtureSelfCheckPassed ? "true" : "false") +
         ",\"cursor_valid\":" + (cursorValid ? "true" : "false") +
         ",\"persistent_key_present\":" +
         (keyPresent ? "true" : "false") +
         ",\"execute_pending\":" + (executePending ? "true" : "false") +
         ",\"arm_request_count\":" + String(armRequestCount) +
         ",\"execute_request_count\":" + String(executeRequestCount) +
         ",\"total_driver_call_count\":" +
         String(totalDriverCallCount) + "," + gpioJson() + "," +
         nvsContractJson() + "}";
}

String driverEvidenceJson(const EpdOperationReport &report) {
  return String("{\"driver_evidence_schema_version\":2,\"operation_id\":") +
         String(report.operationId) +
         ",\"valid\":" + (report.valid ? "true" : "false") +
         ",\"running\":" + (report.running ? "true" : "false") +
         ",\"sequence_ok\":" +
         (report.sequenceOk ? "true" : "false") +
         ",\"wait_timeout\":" +
         (report.waitTimedOut ? "true" : "false") +
         ",\"busy_assertion_missing\":" +
         (report.busyAssertionMissing ? "true" : "false") +
         ",\"mapping_applied\":" +
         (report.mappingApplied ? "true" : "false") +
         ",\"pon_busy_seen\":" + (report.ponBusySeen ? "true" : "false") +
         ",\"drf_busy_seen\":" + (report.drfBusySeen ? "true" : "false") +
         ",\"pof_busy_seen\":" + (report.pofBusySeen ? "true" : "false") +
         ",\"post_psr_busy_seen\":" +
         (report.postPsrBusySeen ? "true" : "false") +
         ",\"pre_command_idle_failure\":" +
         (report.preCommandIdleFailure ? "true" : "false") +
         ",\"failure_stage\":\"" + String(report.failureStage) +
         "\",\"failure_code\":" + String(report.failureCode) +
         ",\"spi_hz\":" + String(report.spiHz) +
         ",\"free_psram_before\":" + String(report.freePsramBefore) +
         ",\"largest_psram_block_before\":" +
         String(report.largestPsramBlockBefore) +
         ",\"input_fnv1a\":" + String(report.inputFrameFnv1a) +
         ",\"cs1_dtm_fnv1a\":" + String(report.cs1DtmFnv1a) +
         ",\"cs2_dtm_fnv1a\":" + String(report.cs2DtmFnv1a) +
         ",\"total_ms\":" + String(report.totalMs) +
         ",\"cs1_upload_ms\":" + String(report.cs1UploadMs) +
         ",\"cs2_upload_ms\":" + String(report.cs2UploadMs) +
         ",\"pon_ms\":" + String(report.ponWaitMs) +
         ",\"drf_ms\":" + String(report.drfWaitMs) +
         ",\"pof_ms\":" + String(report.pofWaitMs) +
         ",\"post_psr_ms\":" + String(report.postPsrWaitMs) +
         ",\"last_wait_stage\":\"" + String(report.lastWaitStage) +
         "\",\"timeout_stage\":\"" + String(report.timeoutStage) +
         "\",\"busy_missing_stage\":\"" +
         String(report.busyMissingStage) +
         "\",\"pre_command_busy_stage\":\"" +
         String(report.preCommandBusyStage) +
         "\",\"safe_finish\":{\"busy_before_pins_low\":" +
         String(report.safeFinishBusyBeforePinsLow) +
         ",\"busy_after_pins_low\":" +
         String(report.safeFinishBusyAfterPinsLow) +
         ",\"busy_after_5ms\":" + String(report.safeFinishBusyAfter5Ms) +
         ",\"final_gpio\":{\"busy\":" + String(report.finalBusyLevel) +
         ",\"rst\":" + String(report.finalRstLevel) +
         ",\"cs\":" + String(report.finalCs1Level) +
         ",\"cs2\":" + String(report.finalCs2Level) + "}}}";
}

void publishNoExecuteReport() {
  publishedReport =
      String("{\"schema_version\":3,\"kind\":") +
      "\"mf1750-ec5-color-lab-recovery-report\",\"valid\":false," + identityJson() +
      ",\"classification\":\"" + kClassification +
      "\",\"boot_nonce\":\"" + bootNonce() +
      "\",\"ordinal\":null,\"descriptor_id\":null,\"action_id\":null," +
      "\"terminal_state\":\"NOT_EXECUTED\",\"result\":false," +
      "\"error\":\"no_execute_report\",\"driver_called\":false," +
      "\"driver_call_count_for_action\":0,\"total_driver_call_count\":" +
      String(totalDriverCallCount) + ",\"phase\":" +
      String(persistentPhase) + ",\"next_ordinal\":" +
      String(nextOrdinal) + ",\"no_retry\":true,\"no_recovery\":true}";
}

void publishFaultReport(const char *error, const ActionDescriptor *action,
                        bool driverCalled, const EpdOperationReport *driver) {
  const String actionFields = action
                                  ? String("\"ordinal\":") +
                                        String(action->ordinal) +
                                        ",\"descriptor_id\":\"" +
                                        action->descriptorId +
                                        "\",\"action_id\":\"" +
                                        action->actionId +
                                        "\",\"role\":\"" + action->role +
                                        "\",\"round\":" +
                                        String(action->round) +
                                        ",\"branch\":\"" + action->branch +
                                        "\""
                                  : String("\"ordinal\":null,"
                                           "\"descriptor_id\":null,"
                                           "\"action_id\":null,"
                                           "\"role\":null,\"round\":null,"
                                           "\"branch\":null");
  publishedReport =
      String("{\"schema_version\":3,\"kind\":") +
      "\"mf1750-ec5-color-lab-recovery-report\",\"valid\":" +
      (driverCalled ? "true" : "false") + "," + identityJson() +
      ",\"classification\":\"" + kClassification +
      "\",\"boot_nonce\":\"" + bootNonce() + "\"," + actionFields +
      ",\"job_id\":" + (action ? String(action->ordinal) : String("null")) +
      ",\"terminal_state\":\"FAULT\",\"result\":false,\"error\":\"" +
      error + "\",\"driver_called\":" +
      (driverCalled ? "true" : "false") +
      ",\"driver_call_count_for_action\":" +
      String(driverCalled ? driverCallCountForAction : 0) +
      ",\"total_driver_call_count\":" + String(totalDriverCallCount) +
      ",\"phase\":" + String(persistentPhase) +
      ",\"phase_name\":\"" + phaseName(persistentPhase) +
      "\",\"next_ordinal\":" + String(nextOrdinal) +
      ",\"no_retry\":true,\"no_recovery\":true" +
      (driver ? String(",\"driver\":") + driverEvidenceJson(*driver)
              : String("")) +
      "}";
}

void enterFault(const char *error, const ActionDescriptor *action,
                bool driverCalled = false,
                const EpdOperationReport *driver = nullptr) {
  executePending = false;
  uint8_t ordinal = action ? action->ordinal : nextOrdinal;
  if (ordinal < 1 || ordinal > kActionCount) ordinal = 1;
  persistCursor(kPhaseFault, ordinal);
  state = RuntimeState::FaultLocked;
  publishFaultReport(error, action, driverCalled, driver);
}

void rejectMutation(int statusCode, const char *error,
                    const ActionDescriptor *action) {
  enterFault(error, action);
  server.send(statusCode, "application/json",
              String("{\"accepted\":false,\"fault_locked\":true,") +
                  "\"error\":\"" + error +
                  "\",\"no_retry\":true,\"no_recovery\":true}");
}

void handleArm() {
  ++armRequestCount;
  if (!refreshCursorEvidence()) {
    rejectMutation(503, "arm_cursor_invalid", nullptr);
    return;
  }
  const ActionDescriptor *action = currentAction();
  if (state != RuntimeState::Ready || persistentPhase != kPhaseReady ||
      !action) {
    rejectMutation(409, "arm_duplicate_complete_or_not_ready", action);
    return;
  }
  const char *contractError =
      validateMutationContract(*action, kArmIntent, false);
  if (contractError) {
    rejectMutation(400, contractError, action);
    return;
  }
  if (!fixtureSelfCheckPassed || !gpioInitialized || !storeReady) {
    rejectMutation(503, "arm_preflight_not_ready", action);
    return;
  }
  armNonceHigh = esp_random();
  armNonceLow = esp_random();
  if ((armNonceHigh | armNonceLow) == 0) armNonceLow = 1;
  driverCallCountForAction = 0;
  if (!persistCursor(kPhaseArmed, action->ordinal)) {
    rejectMutation(503, "persistent_armed_write_failed", action);
    return;
  }
  state = RuntimeState::Armed;
  server.send(
      201, "application/json",
      String("{\"accepted\":true,\"armed\":true,") + identityJson() +
          ",\"classification\":\"" + kClassification +
          "\",\"ordinal\":" + String(action->ordinal) +
          ",\"descriptor_id\":\"" + action->descriptorId +
          "\",\"action_id\":\"" + action->actionId +
          "\",\"role\":\"" + action->role +
          "\",\"round\":" + String(action->round) +
          ",\"branch\":\"" + action->branch +
          "\",\"boot_nonce\":\"" + bootNonce() +
          "\",\"arm_nonce\":\"" + armNonce() +
          "\",\"phase\":1,\"phase_name\":\"ARMED\"," +
          "\"not_hardware_authorization\":true}");
}

void handleExecute() {
  ++executeRequestCount;
  if (!refreshCursorEvidence()) {
    rejectMutation(503, "execute_cursor_invalid", nullptr);
    return;
  }
  const ActionDescriptor *action = currentAction();
  if (state != RuntimeState::Armed || persistentPhase != kPhaseArmed ||
      !action) {
    rejectMutation(409, "execute_duplicate_stale_or_not_armed", action);
    return;
  }
  const char *contractError =
      validateMutationContract(*action, kExecuteIntent, true);
  if (contractError) {
    rejectMutation(400, contractError, action);
    return;
  }
  if (!fixtureSelfCheckPassed || !gpioInitialized || !storeReady ||
      driverCallCountForAction != 0) {
    rejectMutation(503, "execute_preflight_not_ready", action);
    return;
  }
  if (!persistCursor(kPhaseConsumed, action->ordinal)) {
    rejectMutation(503, "persistent_consumed_write_failed", action);
    return;
  }
  jobQueuedAtMs = millis();
  state = RuntimeState::Queued;
  executePending = true;
  server.send(
      202, "application/json",
      String("{\"accepted\":true,\"job_id\":") +
          String(action->ordinal) + "," + identityJson() +
          ",\"classification\":\"" + kClassification +
          "\",\"ordinal\":" + String(action->ordinal) +
          ",\"descriptor_id\":\"" + action->descriptorId +
          "\",\"action_id\":\"" + action->actionId +
          "\",\"role\":\"" + action->role +
          "\",\"round\":" + String(action->round) +
          ",\"branch\":\"" + action->branch +
          "\",\"boot_nonce\":\"" + bootNonce() +
          "\",\"execute_consumed\":true,\"phase\":2," +
          "\"phase_name\":\"CONSUMED\",\"no_retry\":true," +
          "\"no_recovery\":true}");
}

void installRoutes() {
  static const char *headers[] = {
      "Content-Type",      "Content-Length",    "Transfer-Encoding",
      kBuildHeader,        kTestHeader,          kCampaignHeader,
      kActionHeader,       kOrdinalHeader,       kDescriptorHeader,
      kBootNonceHeader,    kArmNonceHeader,      kIntentHeader,
  };
  server.collectHeaders(headers, sizeof(headers) / sizeof(headers[0]));
  server.on(kVersionRoute, HTTP_GET, []() {
    if (requireReadOnlyRequest())
      server.send(200, "application/json", versionJson());
  });
  server.on(kManifestRoute, HTTP_GET, []() {
    if (requireReadOnlyRequest())
      server.send(200, "application/json", manifestJson());
  });
  server.on(kStatusRoute, HTTP_GET, []() {
    if (requireReadOnlyRequest())
      server.send(200, "application/json", statusJson());
  });
  server.on(kReportRoute, HTTP_GET, []() {
    if (requireReadOnlyRequest())
      server.send(200, "application/json", publishedReport);
  });
  server.on(kArmRoute, HTTP_POST, handleArm);
  server.on(kExecuteRoute, HTTP_POST, handleExecute);
  server.onNotFound([]() {
    if (server.method() == HTTP_POST) {
      rejectMutation(404, "unknown_mutation_route", currentAction());
      return;
    }
    server.send(404, "application/json", "{\"error\":\"not_found\"}");
  });
}

void startWiFi() {
  if (strlen(WIFI_STA_SSID) > 0) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_STA_SSID, WIFI_STA_PASSWORD);
    const uint32_t startedAt = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startedAt < 15000UL) {
      delay(250);
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("EC5 COLOR_LAB WiFi STA IP: %s\n",
                    WiFi.localIP().toString().c_str());
      return;
    }
  }
  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
  Serial.printf("EC5 COLOR_LAB WiFi AP IP: %s\n",
                WiFi.softAPIP().toString().c_str());
}

void executePendingAction() {
  if (!executePending) return;
  const ActionDescriptor *action = currentAction();
  if (!refreshCursorEvidence() || persistentPhase != kPhaseConsumed ||
      state != RuntimeState::Queued || !action ||
      driverCallCountForAction != 0) {
    enterFault("runtime_queue_or_cursor_mismatch", action);
    return;
  }

  executePending = false;
  state = RuntimeState::Running;
  jobStartedAtMs = millis();
  ++driverCallCountForAction;
  ++totalDriverCallCount;
  const bool result = epdDisplayCompiledColorLab(action->driverRole);
  jobFinishedAtMs = millis();
  const EpdOperationReport &driver = epdGetLastOperationReport();

  if (!result) {
    persistCursor(kPhaseFault, action->ordinal);
    state = RuntimeState::FaultLocked;
    publishFaultReport("driver_operation_failed", action, true, &driver);
    return;
  }

  const uint8_t completedOrdinal = action->ordinal;
  const uint8_t followingOrdinal = completedOrdinal + 1;
  if (!persistCursor(kPhaseReady, followingOrdinal)) {
    enterFault("persistent_next_ready_write_failed", action, true, &driver);
    return;
  }
  state = followingOrdinal == kTerminalOrdinal ? RuntimeState::Complete
                                               : RuntimeState::Ready;
  publishedReport =
      String("{\"schema_version\":3,\"kind\":") +
      "\"mf1750-ec5-color-lab-recovery-report\",\"valid\":true," + identityJson() +
      ",\"classification\":\"" + kClassification +
      "\",\"boot_nonce\":\"" + bootNonce() +
      "\",\"ordinal\":" + String(completedOrdinal) +
      ",\"descriptor_id\":\"" + action->descriptorId +
      "\",\"action_id\":\"" + action->actionId +
      "\",\"role\":\"" + action->role + "\",\"round\":" +
      String(action->round) + ",\"branch\":\"" + action->branch +
      "\",\"job_id\":" + String(completedOrdinal) +
      ",\"terminal_state\":\"COMPLETE\",\"result\":true," +
      "\"driver_called\":true,\"driver_call_count_for_action\":1," +
      "\"total_driver_call_count\":" + String(totalDriverCallCount) +
      ",\"phase\":0,\"phase_name\":\"READY\",\"next_ordinal\":" +
      String(followingOrdinal) +
      ",\"campaign_complete\":" +
      (followingOrdinal == kTerminalOrdinal ? "true" : "false") +
      ",\"no_retry\":true,\"no_recovery\":true," +
      "\"job_queued_at_ms\":" + String(jobQueuedAtMs) +
      ",\"job_started_at_ms\":" + String(jobStartedAtMs) +
      ",\"job_finished_at_ms\":" + String(jobFinishedAtMs) +
      ",\"driver\":" + driverEvidenceJson(driver) + "}";
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(50);
  Serial.println("\nMF1750 EC5 single-flash COLOR_LAB booting");
  Serial.printf("Build: %s\n", kBuildTag);
  Serial.println("Technical experiment: code values are not colour claims");
  Serial.println("No startup refresh/raw ingress/dither/auto-chain/retry/recovery");

  bootNonceHigh = esp_random();
  bootNonceLow = esp_random();
  if ((bootNonceHigh | bootNonceLow) == 0) bootNonceLow = 1;

  fixtureSelfCheckPassed = epdValidateCompiledColorLabFixtures();
  storeReady = cursorStore.begin(kNvsNamespace, false /* readOnly */);
  const bool cursorValid = refreshCursorEvidence();

  if (!fixtureSelfCheckPassed) {
    state = RuntimeState::FaultLocked;
    publishFaultReport("compiled_fixture_self_check_failed", nullptr, false,
                       nullptr);
  } else if (!storeReady) {
    state = RuntimeState::FaultLocked;
    publishFaultReport("cursor_store_open_failed", nullptr, false, nullptr);
  } else if (!cursorValid) {
    enterFault("persistent_cursor_invalid", nullptr);
  } else if (persistentPhase != kPhaseReady) {
    // A reboot after ARM/EXEC or after any fault never resumes or retries.
    state = RuntimeState::FaultLocked;
    publishFaultReport("non_ready_cursor_seen_at_boot", currentAction(), false,
                       nullptr);
  } else {
    epdBegin();
    gpioInitialized = true;
    state = nextOrdinal == kTerminalOrdinal ? RuntimeState::Complete
                                             : RuntimeState::Ready;
    publishNoExecuteReport();
  }

  startWiFi();
  installRoutes();
  server.begin();
  Serial.printf("Read-only manifest: %s\n", kManifestRoute);
  Serial.printf("Bodyless per-action ARM: POST %s\n", kArmRoute);
  Serial.printf("Bodyless per-action EXECUTE: POST %s\n", kExecuteRoute);
}

void loop() {
  server.handleClient();
  executePendingAction();
  delay(2);
}
