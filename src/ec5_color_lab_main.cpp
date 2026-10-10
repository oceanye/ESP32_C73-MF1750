#include <Arduino.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <esp_system.h>

#include <cstdio>
#include <cstring>

#include "epd_config.h"
#include "epd_driver.h"

// Single-flash, fixed-frame EC5 colour laboratory. Every visible action is
// independently armed and executed. There is no startup refresh, raw frame
// ingress, automatic chaining, retry, recovery, or NVS clear endpoint.
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
    "TECHNICAL_EXPERIMENT_NO_PHYSICAL_COLOUR_CLAIM";
static constexpr const char *kIdentityRevision = "color-lab-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_COLOR_LAB_DEVICE_V1";
static constexpr const char *kLayoutId =
    "EC5_COLOR_LAB_COMPOSED_FIXED_FRAMES_V1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_COLOR_LAB_V1_2026-08-09";
static constexpr const char *kTestId = "EC5-COLOR-LAB-V1";
static constexpr const char *kCampaignId = "EC5_COLOR_LAB_CAMPAIGN_V1";
static constexpr const char *kContractId =
    "7a5c7f1ecf5265fdffe0b3b3d2448c00106d49f128cb3a15e5b41ad7e97b968a";

static constexpr const char *kNvsNamespace = "mf1750_ec5cl";
static constexpr const char *kNvsKey = "cursor";

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
    "ARM_ONE_FIXED_COLOR_LAB_ACTION_NOT_HARDWARE_AUTHORIZATION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ONE_FIXED_COLOR_LAB_ACTION_NOT_HARDWARE_AUTHORIZATION";

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
                 "106bb9713eeb5718953d9cc6cbf40339932e19693b5d41b1c4287ba04bec2d51",
                 "ecbd9684f901a33c2a8f483b9cdd2795c3a759aa6f5fd4e0ea514b658fbfcdbf",
                 nullptr),
    {2, EpdColorLabRole::U07Isolated, "U07_ISOLATED", 0, "ISOLATED_U07",
     "698ff0f58845e07ddfd2d797bd831d6cff4d8bd753691ae22fd0645557c23988",
     "b822084c1bc3730b48baa2c043735a160d805d767ace38194211401717468f99",
     "ecbd9684f901a33c2a8f483b9cdd2795c3a759aa6f5fd4e0ea514b658fbfcdbf",
     kU07IsolatedFrameSha256, kU07IsolatedDtmSha256,
     kU07IsolatedDtmSha256},
    WHITE_ACTION(3, 0, "AFTER_ISOLATED_U07_WHITE",
                 "d3e89aba9170c87d9378d228207287d73781bd602365dd7682867a8c3b03661d",
                 "dda166efc7955ab35d57b5d90ac773c17130bbdf86671f6819e0508574ab383c",
                 "b822084c1bc3730b48baa2c043735a160d805d767ace38194211401717468f99"),
    {4, EpdColorLabRole::Atlas, "ATLAS_0_7", 0, "BALANCED_EIGHTCODE_ATLAS",
     "8bcd1e2da65df6f8551c567ec341e9cecf55a052f69ffba3e6f45a438ddbcf31",
     "f4f029aad202d04fe1da3dc62ce32a3100ee2af7197159b05667a3cbbbfc7a36",
     "dda166efc7955ab35d57b5d90ac773c17130bbdf86671f6819e0508574ab383c",
     kAtlasFrameSha256, kAtlasCs1DtmSha256, kAtlasCs2DtmSha256},
    WHITE_ACTION(5, 0, "AFTER_ATLAS_WHITE",
                 "620188f5d8e126ffe095eb7864b9cb1028d63496d618c9fef2774b45cd78553c",
                 "5dc1934ef1803c6ea669ca16906a30cdfde819f57577b605461e7fdad792b06e",
                 "f4f029aad202d04fe1da3dc62ce32a3100ee2af7197159b05667a3cbbbfc7a36"),
    {6, EpdColorLabRole::U04SixStatePrimer, "U04_SIXSTATE_PRIMER", 1,
     "U04_SIXSTATE",
     "9efa0228b2d3db171d095f18248a8f3b5c7e4346a81ca31076262720891ac275",
     "225888ba99a09c0756fc5f71d083ab0fadae789128d6e7c07a6e4cd84be8af41",
     "5dc1934ef1803c6ea669ca16906a30cdfde819f57577b605461e7fdad792b06e",
     kPrimerFrameSha256, kPrimerDtmSha256, kPrimerDtmSha256},
    {7, EpdColorLabRole::U04SixStateTarget, "U04_SIXSTATE_TARGET", 1,
     "U04_SIXSTATE",
     "a5789683e8f85b33128fafa9cc7aabc26701f95b0ca20fdd4575619269ae7a31",
     "8bd418db27f6f49e6a97b3bf2130c6a0388cace39feebfd158c9bd2496e5eb3c",
     "225888ba99a09c0756fc5f71d083ab0fadae789128d6e7c07a6e4cd84be8af41",
     kU04TargetFrameSha256, kU04TargetDtmSha256, kU04TargetDtmSha256},
    WHITE_ACTION(8, 1, "AFTER_U04_SIXSTATE_WHITE",
                 "64a6ae2a388093a75f6c577a05a6c3902322f07fe14019c9e95744a878d1c363",
                 "cf238fe37eb76a3a415fdea5d080fd5980e9e03d627867c6ddc6628c69b6ba51",
                 "8bd418db27f6f49e6a97b3bf2130c6a0388cace39feebfd158c9bd2496e5eb3c"),
    {9, EpdColorLabRole::U07SixStatePrimer, "U07_SIXSTATE_PRIMER", 1,
     "U07_SIXSTATE",
     "a58954c73476abb3a56dc86e64df2eba69cf50b29810a8ba6f16109ca1506983",
     "9424b75e30382c36a31e3cd5ad591cef2b830373aff223ceefa52b391ed84f18",
     "cf238fe37eb76a3a415fdea5d080fd5980e9e03d627867c6ddc6628c69b6ba51",
     kPrimerFrameSha256, kPrimerDtmSha256, kPrimerDtmSha256},
    {10, EpdColorLabRole::U07SixStateTarget, "U07_SIXSTATE_TARGET", 1,
     "U07_SIXSTATE",
     "43d19a37d2f8058b2455691b1527f5484179bff523ffa5b2dcf1972bde0bf078",
     "6ea14f9b7b635857a822e2c578a801a3b1485d9332b14ab14d46edcc68a88dd0",
     "9424b75e30382c36a31e3cd5ad591cef2b830373aff223ceefa52b391ed84f18",
     kU07TargetFrameSha256, kU07TargetDtmSha256, kU07TargetDtmSha256},
    WHITE_ACTION(11, 1, "AFTER_U07_SIXSTATE_WHITE",
                 "130b2acb3754424ec5ab22243f5439321377309fe2cfc8f5afb94e7a047633c7",
                 "800c89da0e12d45a70a75a7ca6bd6508b9ff895ba7d19e1a3378c29ecb19193e",
                 "6ea14f9b7b635857a822e2c578a801a3b1485d9332b14ab14d46edcc68a88dd0"),
    {12, EpdColorLabRole::U04SixStatePrimer, "U04_SIXSTATE_PRIMER", 2,
     "U04_SIXSTATE",
     "a19129e292ac20d4c1d18849c983f841904f3c373773cf313591247f5dc09ab7",
     "eae829a63f626a8532920b79daf710c965b5e18840f9cdcae2372356a83d676f",
     "800c89da0e12d45a70a75a7ca6bd6508b9ff895ba7d19e1a3378c29ecb19193e",
     kPrimerFrameSha256, kPrimerDtmSha256, kPrimerDtmSha256},
    {13, EpdColorLabRole::U04SixStateTarget, "U04_SIXSTATE_TARGET", 2,
     "U04_SIXSTATE",
     "ab689d4a91cbf56613c0c2d44d09976485273df591d464be85adf7247902b91c",
     "1458bd2648c4513163740c30de6d2024a09decf74ba3d1a89a5c7819da676121",
     "eae829a63f626a8532920b79daf710c965b5e18840f9cdcae2372356a83d676f",
     kU04TargetFrameSha256, kU04TargetDtmSha256, kU04TargetDtmSha256},
    WHITE_ACTION(14, 2, "AFTER_U04_SIXSTATE_WHITE",
                 "bf364248de6476bb180db1d3352ea4db78a5b19486f0f91b536811dfa2412c37",
                 "f9ea7c4c8fbad989de3860511d64a37ac107b8bc71634e16bc918c61ac6c1503",
                 "1458bd2648c4513163740c30de6d2024a09decf74ba3d1a89a5c7819da676121"),
    {15, EpdColorLabRole::U07SixStatePrimer, "U07_SIXSTATE_PRIMER", 2,
     "U07_SIXSTATE",
     "f2e152cd95c32a561fa16fb02a6cf73499cd3d760fd674784e011cefc30c544a",
     "813ea6f1bf39a76b77a0b0e9100aaba1e068410d2411822b8a5d3f34e817fd1e",
     "f9ea7c4c8fbad989de3860511d64a37ac107b8bc71634e16bc918c61ac6c1503",
     kPrimerFrameSha256, kPrimerDtmSha256, kPrimerDtmSha256},
    {16, EpdColorLabRole::U07SixStateTarget, "U07_SIXSTATE_TARGET", 2,
     "U07_SIXSTATE",
     "69aa51060064fc3d456f56382a9caedc53839738eb0a352c1d0397bed8f5e75f",
     "13e9fb6bfbbac5c5e2bd6061684e522fb4c07cc1cf2ae79a1b35022d43dd9861",
     "813ea6f1bf39a76b77a0b0e9100aaba1e068410d2411822b8a5d3f34e817fd1e",
     kU07TargetFrameSha256, kU07TargetDtmSha256, kU07TargetDtmSha256},
    WHITE_ACTION(17, 2, "AFTER_U07_SIXSTATE_WHITE",
                 "bf315ec92cce0361692be6a136e2a28f4551d35151d53e736d5d829f7642d31a",
                 "c6f3668eef796b3e43dea227772a1b1627b2ea4eb61d9999b62bf8648a7f858b",
                 "13e9fb6bfbbac5c5e2bd6061684e522fb4c07cc1cf2ae79a1b35022d43dd9861"),
    {18, EpdColorLabRole::U04SixStatePrimer, "U04_SIXSTATE_PRIMER", 3,
     "U04_SIXSTATE",
     "2f08a1ec8c7619d7f714bf83545f5d2350faa6c1d077d1f2c5e97c10c85cf4d8",
     "bb3045f988d84d4e3c70f2acea4cedcbaad55fae4b002cc99067f39cc0232c6f",
     "c6f3668eef796b3e43dea227772a1b1627b2ea4eb61d9999b62bf8648a7f858b",
     kPrimerFrameSha256, kPrimerDtmSha256, kPrimerDtmSha256},
    {19, EpdColorLabRole::U04SixStateTarget, "U04_SIXSTATE_TARGET", 3,
     "U04_SIXSTATE",
     "ec823a3a987bd09c8fa4e56293edb0e185db50bdb9499b17c586bb7fe44b7757",
     "588222c323994fc0ec0e12816465345f9abc363b6f4eea76b16a0db61f8edc23",
     "bb3045f988d84d4e3c70f2acea4cedcbaad55fae4b002cc99067f39cc0232c6f",
     kU04TargetFrameSha256, kU04TargetDtmSha256, kU04TargetDtmSha256},
    WHITE_ACTION(20, 3, "AFTER_U04_SIXSTATE_WHITE",
                 "9efa4b208cd312c16379141225782d1c90d3c3a4e115e6013a3f3768e2da97d6",
                 "d70883ca065ed47029f9273640329eaea1533a4eef46a763a2972aca0936794a",
                 "588222c323994fc0ec0e12816465345f9abc363b6f4eea76b16a0db61f8edc23"),
    {21, EpdColorLabRole::U07SixStatePrimer, "U07_SIXSTATE_PRIMER", 3,
     "U07_SIXSTATE",
     "b209a347df7c442e1de0b2a72e9ec209a9d4e95b309eaf9248b8ff08ac87091c",
     "f315c38bdff3a3c82a8e45df1c71fb7183902b03bb694477f4ba6bb20e98b875",
     "d70883ca065ed47029f9273640329eaea1533a4eef46a763a2972aca0936794a",
     kPrimerFrameSha256, kPrimerDtmSha256, kPrimerDtmSha256},
    {22, EpdColorLabRole::U07SixStateTarget, "U07_SIXSTATE_TARGET", 3,
     "U07_SIXSTATE",
     "2d80708af9fc23d0e525ec134f284869c5da12deeb6e3c46065667a3a70c0d03",
     "d6140a5bd60c25c500cac79f60e855f643370c3ccab225eb4e4b4bfb44d12d51",
     "f315c38bdff3a3c82a8e45df1c71fb7183902b03bb694477f4ba6bb20e98b875",
     kU07TargetFrameSha256, kU07TargetDtmSha256, kU07TargetDtmSha256},
    WHITE_ACTION(23, 3, "AFTER_U07_SIXSTATE_WHITE",
                 "6e4689c5f0aed21cea8cf801bb1e9b91db1975a859b44591b3390a4f8f6586dd",
                 "db8297118746ae176d6484579834eb1003a745b23cb158198a720ef6621fc8b7",
                 "d6140a5bd60c25c500cac79f60e855f643370c3ccab225eb4e4b4bfb44d12d51"),
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
         "\"mf1750-ec5-color-lab-version\"," + identityJson() +
         ",\"classification\":\"" + kClassification +
         "\",\"layout_id\":\"" + kLayoutId +
         "\",\"driver_api_version\":\"" + EPD_DRIVER_API_VERSION +
         "\",\"action_count\":23,\"automatic_execute\":false," +
         "\"automatic_chaining\":false,\"startup_refresh\":false," +
         "\"raw_frame_ingress\":false,\"dither\":false," +
         "\"retry\":false,\"recovery\":false," + nvsContractJson() + "}";
}

String manifestJson() {
  String output = String("{\"schema_version\":3,\"kind\":") +
                  "\"mf1750-ec5-color-lab-manifest\"," + identityJson() +
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
  output += String("],") + nvsContractJson() + "}";
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
         "\"mf1750-ec5-color-lab-status\"," + identityJson() +
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
      "\"mf1750-ec5-color-lab-report\",\"valid\":false," + identityJson() +
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
      "\"mf1750-ec5-color-lab-report\",\"valid\":" +
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
      "\"mf1750-ec5-color-lab-report\",\"valid\":true," + identityJson() +
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
