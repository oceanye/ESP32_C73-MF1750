// Warm-session state machine layered on the exact V4 L535/PTLW primitives.
// The cold V4 entry points are renamed and never referenced by this build.
// This file owns the only reachable display entry point: one prepare/PON,
// three DRF-only cropped updates, then one full-window white DRF and safe POF.

#include "ec5_partial_hold_warm_session_v1_identity.inc"

static_assert(EPD_SPI_DEFAULT_HZ == 1000000,
              "warm session is frozen to the proven 1 MHz transport");
static_assert(EPD_BUSY_IDLE_LEVEL == HIGH,
              "warm session requires the proven BUSY idle-HIGH contract");

namespace {

namespace warm = mf1750_partial_hold_warm_session_v1;

static constexpr const char *WARM_FAILURE_SEQUENCE = "warm_session_sequence";
static constexpr const char *WARM_FAILURE_EXPIRED = "warm_session_expired";
static constexpr const char *WARM_FAILURE_PROFILE = "warm_profile_contract";
static constexpr const char *WARM_FAILURE_PREPARE = "warm_prepare_once";
static constexpr const char *WARM_FAILURE_GLOBAL = "warm_global_config_once";
static constexpr const char *WARM_FAILURE_CS1_LUT = "warm_cs1_lut_once";
static constexpr const char *WARM_FAILURE_CS2_LUT = "warm_cs2_lut_once";
static constexpr const char *WARM_FAILURE_STREAM = "warm_stream_identity";
static constexpr const char *WARM_FAILURE_PON = "warm_pon_once";
static constexpr const char *WARM_FAILURE_DRF = "warm_drf_only";
static constexpr const char *WARM_FAILURE_POF = "warm_final_safe_pof";

EpdPartialHoldWarmState warmState = EpdPartialHoldWarmState::Cold;
uint32_t warmDeadlineStartedMs = 0;
bool warmPanelPowered = false;
bool warmActionRunning = false;
uint8_t warmPrepareCount = 0;
uint8_t warmPonCount = 0;
uint8_t warmPofCount = 0;

bool warmStateActive(EpdPartialHoldWarmState state) {
  return state == EpdPartialHoldWarmState::WarmExpectRed ||
         state == EpdPartialHoldWarmState::WarmExpectBlue ||
         state == EpdPartialHoldWarmState::WarmExpectGreen ||
         state == EpdPartialHoldWarmState::WarmExpectRecovery;
}

bool warmRoleMap(EpdPartialHoldWarmRole role, EpdChromaGridRole *v4Role,
                 EpdPartialHoldWarmState *required,
                 EpdPartialHoldWarmState *following) {
  if (!v4Role || !required || !following) return false;
  switch (role) {
    case EpdPartialHoldWarmRole::WhiteBaseline:
      *v4Role = EpdChromaGridRole::White;
      *required = EpdPartialHoldWarmState::Cold;
      *following = EpdPartialHoldWarmState::WarmExpectRed;
      return true;
    case EpdPartialHoldWarmRole::RedA:
      *v4Role = EpdChromaGridRole::Source;
      *required = EpdPartialHoldWarmState::WarmExpectRed;
      *following = EpdPartialHoldWarmState::WarmExpectBlue;
      return true;
    case EpdPartialHoldWarmRole::BlueB:
      *v4Role = EpdChromaGridRole::Mid;
      *required = EpdPartialHoldWarmState::WarmExpectBlue;
      *following = EpdPartialHoldWarmState::WarmExpectGreen;
      return true;
    case EpdPartialHoldWarmRole::GreenC:
      *v4Role = EpdChromaGridRole::Target;
      *required = EpdPartialHoldWarmState::WarmExpectGreen;
      *following = EpdPartialHoldWarmState::WarmExpectRecovery;
      return true;
    case EpdPartialHoldWarmRole::WhiteRecovery:
      *v4Role = EpdChromaGridRole::White;
      *required = EpdPartialHoldWarmState::WarmExpectRecovery;
      *following = EpdPartialHoldWarmState::Closed;
      return true;
  }
  return false;
}

bool warmLeaseValid() {
  return !warmStateActive(warmState) ||
         millis() - warmDeadlineStartedMs <= warm::kMaxWarmGapMs;
}

void warmFinishPinsWithoutPoweredPanel() {
  epdStopHardwareSpi();
  epdHoldPanelPinsLow();
}

bool warmFail(uint32_t started, const char *stage, int32_t code = 0) {
  epdRecordFailure(stage, code);
  warmState = EpdPartialHoldWarmState::Fault;
  if (warmPanelPowered) {
    // Successful actions park both CS lines HIGH with neither controller
    // active. Re-select both before the fail-safe command so timeout, HTTP
    // contract faults, and NVS faults cannot emit an unselected no-op POF.
    setActiveControllers(true, true);
    epdRequestFailSafePowerOff("warm session fail-safe POF");
    warmPanelPowered = false;
    ++warmPofCount;
  } else {
    warmFinishPinsWithoutPoweredPanel();
  }
  warmActionRunning = false;
  return epdFinishOperation(started, false);
}

bool warmPowerOnOnceAndRefresh() {
  if (warmPrepareCount != 1 || warmPonCount != 0 || warmPanelPowered) {
    return false;
  }
  setActiveControllers(true, true);
  if (!epdRequireIdleBeforeCommand("PON")) return false;
  epdCommand(PON);
  // Treat the panel as powered from the instant PON is issued so every
  // subsequent failure path requests a fail-safe POF, even if BUSY evidence
  // for PON itself is malformed.
  ++warmPonCount;
  warmPanelPowered = true;
  if (!epdWaitBusyThenIdle("PON")) return false;
  epdCommand(BTST2);
  epdData(0x6F);
  epdData(0x1F);
  epdData(0x17);
  epdData(0x49);
  if (!epdRequireIdleBeforeCommand("DRF")) return false;
  epdCommand(DRF);
  epdData(0x00);
  return epdWaitBusyThenIdle("DRF");
}

bool warmRefreshWithoutPowerTransition() {
  if (!warmPanelPowered || warmPonCount != 1 || warmPrepareCount != 1 ||
      warmPofCount != 0) {
    return false;
  }
  setActiveControllers(true, true);
  epdCommand(CDI);
  epdData(0xFF);
  if (!epdRequireIdleBeforeCommand("DRF")) return false;
  epdCommand(DRF);
  epdData(0x00);
  return epdWaitBusyThenIdle("DRF");
}

bool warmFinalSafePowerOff() {
  if (!warmPanelPowered || warmPonCount != 1 || warmPofCount != 0) {
    return false;
  }
  setActiveControllers(true, true);
  if (!epdRequireIdleBeforeCommand("POF")) return false;
  epdCommand(POF);
  epdData(0x00);
  if (!epdWaitBusyThenIdle("POF")) return false;
  ++warmPofCount;
  warmPanelPowered = false;
  delay(10);
  return epdPostDisplayPowerCut();
}

bool warmStreamAndCheck(EpdPartialHoldWarmRole role,
                        EpdChromaGridRole v4Role, uint8_t *frame,
                        const PhValidation &validation) {
  const size_t roleIndex = phRoleIndex(v4Role);
  const bool baseline = role == EpdPartialHoldWarmRole::WhiteBaseline;
  const bool recovery = role == EpdPartialHoldWarmRole::WhiteRecovery;
  const bool fullWhite = baseline || recovery;
  const ph::Window *window =
      fullWhite ? nullptr : &ph::kWindows[roleIndex - 1];
  const size_t dtmBytes = fullWhite
                              ? EPD_CONTROLLER_FRAME_BYTES
                              : static_cast<size_t>(window->width) *
                                    window->height / 2;

  if (!baseline) {
    if (recovery) {
      const ph::Window fullController = {
          0, 0, EPD_CONTROLLER_WIDTH, EPD_HEIGHT, ph::kWhiteCode,
          ph::kWhiteCode};
      // Keep the same exact 0x83 nine-byte, inclusive x+w-1/y+h-1 wire
      // contract for the final full-controller recovery window.
      phWritePartialWindow(fullController);
    } else {
      phWritePartialWindow(*window);
    }
  }

  const uint8_t cs1Code = fullWhite ? ph::kWhiteCode : window->cs1Code;
  const uint8_t cs2Code = fullWhite ? ph::kWhiteCode : window->cs2Code;
  const uint32_t cs1Started = millis();
  diagnosticReport.cs1DtmFnv1a =
      fullWhite ? epdStreamPackedFrameController(frame, false)
                : phStreamUniformDtm(false, dtmBytes, cs1Code);
  diagnosticReport.cs1UploadMs = millis() - cs1Started;
  const uint32_t cs2Started = millis();
  diagnosticReport.cs2DtmFnv1a =
      fullWhite ? epdStreamPackedFrameController(frame, true)
                : phStreamUniformDtm(true, dtmBytes, cs2Code);
  diagnosticReport.cs2UploadMs = millis() - cs2Started;
  diagnosticReport.mappingApplied = true;
  return diagnosticReport.cs1DtmFnv1a == validation.cs1DtmFnv1a &&
         diagnosticReport.cs2DtmFnv1a == validation.cs2DtmFnv1a;
}

}  // namespace

bool epdValidateCompiledPartialHoldWarmSessionFixtures() {
  const ph::Window fullController = {
      0, 0, EPD_CONTROLLER_WIDTH, EPD_HEIGHT, ph::kWhiteCode,
      ph::kWhiteCode};
  if (!phLayoutValid() || !ph::kSeparateCsWindowCommands ||
      ph::kPtlwYEndOneMore || ph::kPartialWindowCommand != 0x83 ||
      ph::kPartialWindowPayloadBytes != 9 || ph::kWhiteCode != 7 ||
      !phWindowValid(fullController)) {
    return false;
  }
  int32_t profileError = 0;
  if (!phValidateRuntimeLutProfile(&profileError)) return false;
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return false;
  static constexpr EpdChromaGridRole kRoles[] = {
      EpdChromaGridRole::White,
      EpdChromaGridRole::Source,
      EpdChromaGridRole::Mid,
      EpdChromaGridRole::Target,
  };
  bool valid = true;
  for (const EpdChromaGridRole role : kRoles) {
    PhValidation validation;
    if (!phValidateRole(role, frame, &validation)) {
      valid = false;
      break;
    }
  }
  std::free(frame);
  return valid;
}

bool epdDisplayCompiledPartialHoldWarmSession(EpdPartialHoldWarmRole role) {
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  warmActionRunning = true;
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);

  EpdChromaGridRole v4Role;
  EpdPartialHoldWarmState required;
  EpdPartialHoldWarmState following;
  if (!warmRoleMap(role, &v4Role, &required, &following) ||
      warmState != required) {
    return warmFail(started, WARM_FAILURE_SEQUENCE);
  }
  if (required != EpdPartialHoldWarmState::Cold && !warmLeaseValid()) {
    return warmFail(started, WARM_FAILURE_EXPIRED);
  }

  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return warmFail(started, PH_FAILURE_ALLOCATION);
  PhValidation validation;
  if (!phValidateRole(v4Role, frame, &validation)) {
    std::free(frame);
    return warmFail(started, validation.failureStage,
                    validation.failureCode);
  }
  diagnosticReport.inputFrameFnv1a = validation.frameFnv1a;
  int32_t profileError = 0;
  if (!phValidateRuntimeLutProfile(&profileError)) {
    std::free(frame);
    return warmFail(started, WARM_FAILURE_PROFILE, profileError);
  }

  if (role == EpdPartialHoldWarmRole::WhiteBaseline) {
    if (warmPrepareCount != 0 || warmPonCount != 0 || warmPofCount != 0 ||
        !epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) {
      std::free(frame);
      return warmFail(started, WARM_FAILURE_PREPARE);
    }
    ++warmPrepareCount;
    if (!phApplyRuntimeLutGlobalConfig()) {
      std::free(frame);
      return warmFail(started, WARM_FAILURE_GLOBAL);
    }
    if (!phUploadRuntimeLutToController(false)) {
      std::free(frame);
      return warmFail(started, WARM_FAILURE_CS1_LUT);
    }
    if (!phUploadRuntimeLutToController(true)) {
      std::free(frame);
      return warmFail(started, WARM_FAILURE_CS2_LUT);
    }
  } else if (warmPrepareCount != 1 || warmPonCount != 1 ||
             warmPofCount != 0 || !warmPanelPowered ||
             !hardwareSpiStarted) {
    std::free(frame);
    return warmFail(started, WARM_FAILURE_SEQUENCE);
  }

  const bool streamOk =
      warmStreamAndCheck(role, v4Role, frame, validation);
  std::free(frame);
  if (!streamOk) return warmFail(started, WARM_FAILURE_STREAM);

  bool refreshOk = false;
  if (role == EpdPartialHoldWarmRole::WhiteBaseline) {
    refreshOk = warmPowerOnOnceAndRefresh();
    if (!refreshOk) return warmFail(started, WARM_FAILURE_PON);
  } else {
    refreshOk = warmRefreshWithoutPowerTransition();
    if (!refreshOk) return warmFail(started, WARM_FAILURE_DRF);
  }
  if (role == EpdPartialHoldWarmRole::WhiteRecovery &&
      !warmFinalSafePowerOff()) {
    return warmFail(started, WARM_FAILURE_POF);
  }

  warmState = following;
  warmDeadlineStartedMs = warmStateActive(warmState) ? millis() : 0;
  warmActionRunning = false;
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  if (warmState != EpdPartialHoldWarmState::Closed) {
    // While the panel remains powered, park both chip-selects HIGH between
    // HTTP actions. After final POF, epdPostDisplayPowerCut has deliberately
    // held every panel-facing pin LOW; do not undo that safe state.
    setActiveControllers(false, false);
  }
  return epdFinishOperation(started, true);
}

bool epdServicePartialHoldWarmSession() {
  if (warmActionRunning || !warmStateActive(warmState) || warmLeaseValid()) {
    return warmState != EpdPartialHoldWarmState::Fault;
  }
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  warmActionRunning = true;
  return warmFail(started, WARM_FAILURE_EXPIRED);
}

bool epdAbortPartialHoldWarmSession(const char *failureStage) {
  if (warmState == EpdPartialHoldWarmState::Fault) return false;
  if (warmState == EpdPartialHoldWarmState::Closed) return true;
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  warmActionRunning = true;
  return warmFail(started,
                  failureStage ? failureStage : WARM_FAILURE_SEQUENCE);
}

EpdPartialHoldWarmState epdGetPartialHoldWarmSessionState() {
  return warmState;
}

uint32_t epdGetPartialHoldWarmSessionRemainingMs() {
  if (!warmStateActive(warmState)) return 0;
  const uint32_t elapsed = millis() - warmDeadlineStartedMs;
  return elapsed >= warm::kMaxWarmGapMs ? 0 : warm::kMaxWarmGapMs - elapsed;
}
