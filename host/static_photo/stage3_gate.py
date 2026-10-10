"""Compile-time-equivalent hard block for all stage-three LUT activity."""

from __future__ import annotations

from dataclasses import dataclass


class Stage3BlockedError(RuntimeError):
    """Raised for every LUT request until a separate implementation is reviewed."""


@dataclass(frozen=True)
class Stage3EvidenceStatus:
    logic_analyzer_available: bool = False
    logic_analyzer_self_test_passed: bool = False
    factory_otp_capture_bound: bool = False
    ram_lut_command_evidence_g3: bool = False
    unmodified_equivalent_lut_g4: bool = False

    @property
    def evidence_gates_complete(self) -> bool:
        return all(
            (
                self.logic_analyzer_available,
                self.logic_analyzer_self_test_passed,
                self.factory_otp_capture_bound,
                self.ram_lut_command_evidence_g3,
                self.unmodified_equivalent_lut_g4,
            )
        )


def request_lut_write(_status: Stage3EvidenceStatus) -> None:
    """Reject LUT writes even if synthetic booleans claim all evidence gates.

    A future reviewed implementation must replace this function and bind exact
    artifacts.  Boolean flags alone can never authorize a physical write.
    """

    raise Stage3BlockedError(
        "stage-three LUT write is not implemented or authorized; G3/G4 evidence "
        "must be artifact-bound in a separate reviewed release"
    )
