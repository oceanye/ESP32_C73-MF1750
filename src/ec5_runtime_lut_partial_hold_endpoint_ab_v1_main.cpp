// The reviewed repeat-PTLW host/device state machine supplies factory-OTP
// white anchors, immutable ARM/EXECUTE actions, NVS isolation, and BUSY=1
// gates at ARM, EXECUTE, and dispatch.  Build flags select the isolated A/B
// identity and routes before this implementation is included.
#include "ec5_runtime_lut_partial_hold_repeat_ptlw_v1_main.cpp"
