#!/usr/bin/env python3
"""Source-shaped C23 adapter for the frozen one-shot runner.

The frozen parent validator expects five manifest-only fields inside the
version profile.  The C23 firmware source deliberately emits those fields at
the manifest root instead.  This entry point requires the five keys to be
absent from the device version profile, supplies them only to the legacy
subset validator, and otherwise delegates the unchanged C23 runner.

The C23 firmware also prefixes the terminal driver discriminator with
``c23_`` while the frozen parent validator checks the unprefixed C20 name.
This adapter requires the source-shaped C23 key, rejects the legacy key on the
wire, and aliases it only inside the frozen terminal validator.  No device
request, action count, claim rule, or visible-refresh behavior is changed.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from tools import mf1750_ec5_h3_c23_matched_control_physical_once as c23


_MANIFEST_ONLY_PROFILE_KEYS = (
    "control_design",
    "strict_payload_only_control",
    "time_matched_control",
    "dummy_clocks_inserted",
    "empty_r20_or_r21_commands_inserted",
)
_ORIGINAL_EXPECT_VERSION = c23._engine._expect_version  # noqa: SLF001
_ORIGINAL_EXPECT_TERMINAL_DRIVER = (  # noqa: SLF001
    c23._engine._expect_terminal_driver
)


def _expect_source_shaped_version(
    value: Mapping[str, Any], context: Any, ordinal: int
) -> None:
    if ordinal != 1:
        _ORIGINAL_EXPECT_VERSION(value, context, ordinal)
        return
    profile = value.get("profile")
    if not isinstance(profile, Mapping):
        raise c23.MatchedControlPhysicalError(
            "device C23 version profile is absent"
        )
    if any(key in profile for key in _MANIFEST_ONLY_PROFILE_KEYS):
        raise c23.MatchedControlPhysicalError(
            "device C23 version contains unexpected manifest-only profile keys"
        )
    normalized = deepcopy(dict(value))
    normalized["profile"] = {
        **dict(profile),
        "control_design": c23.contract.CONTROL_DESIGN,
        "strict_payload_only_control": False,
        "time_matched_control": False,
        "dummy_clocks_inserted": False,
        "empty_r20_or_r21_commands_inserted": False,
    }
    _ORIGINAL_EXPECT_VERSION(normalized, context, ordinal)


def _expect_source_shaped_terminal_driver(
    value: Any, context: Any, ordinal: int
) -> None:
    if not isinstance(value, Mapping):
        _ORIGINAL_EXPECT_TERMINAL_DRIVER(value, context, ordinal)
        return
    source_key = "c23_matched_no_r20_r21_control"
    legacy_key = "matched_no_r20_r21_control"
    if legacy_key in value:
        raise c23.MatchedControlPhysicalUnknown(
            "device C23 terminal driver contains unexpected legacy discriminator"
        )
    wanted = ordinal == 1
    if value.get(source_key) is not wanted:
        raise c23.MatchedControlPhysicalUnknown(
            f"terminal driver {source_key} evidence differs"
        )
    normalized = deepcopy(dict(value))
    del normalized[source_key]
    normalized[legacy_key] = wanted
    _ORIGINAL_EXPECT_TERMINAL_DRIVER(normalized, context, ordinal)


def install_overrides() -> None:
    """Install only the two source-shape aliases in the isolated C23 engine."""

    c23._engine._expect_version = _expect_source_shaped_version  # noqa: SLF001
    c23._engine._expect_terminal_driver = (  # noqa: SLF001
        _expect_source_shaped_terminal_driver
    )


def main(argv: Sequence[str] | None = None) -> int:
    install_overrides()
    return c23.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
