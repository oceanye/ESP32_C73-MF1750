#!/usr/bin/env python3
"""PAL1-R1-D1 defect reproduction / fix verification probe; fully offline.

Compiles each package's generated driver gate path (phRoleIndex/phRoleValid/
phLayoutValid/phBuildExpectedFrame + the exact compiled fixture kRoles
declaration) with MSVC and runs the fixture-equivalent check: every role the
compiled fixture self-check validates must have an in-bounds identity entry
whose histogram and frame FNV match the freshly built frame.

Expected: PAL1_CAL_20260924_R1 FAILS (kRoles={Source,Mid,Target} vs
kActions[2] — Mid/Target out of bounds), PAL1_CAL_20260924_R2 PASSES. This is
the native coverage the R1 audit lacked (its protocol fixture stubs
epdValidateCompiledChromaGridFixtures() and its probe never touched
ph::kActions).

No hardware, serial, network, relay or camera access. The sha256 digest
comparison of phValidateRole is not reproduced (no desktop mbedTLS); the
bounds+histogram+FNV surface is exactly what the defect broke.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import mf1750_lightness_history_firmware as base_firmware  # noqa: E402
from tools import mf1750_pal1_native_audit as audit  # noqa: E402
from tools.mf1750_lightness_history_native_audit import compiler_environment  # noqa: E402

DEFAULT_OUT = ROOT / ".test-output/offline/PAL1_FIXTURE_DEFECT_REPRO_20260924_R1"


def probe_source(driver_text, identity_name, cpp_namespace):
    begin = driver_text.index("size_t phRoleIndex(")
    end = driver_text.index("bool phDigestMatchesHex(")
    segment = driver_text[begin:end]
    build = driver_text.index("bool phBuildExpectedFrame(")
    frame_fn = driver_text[build:driver_text.index("\n}\n", build) + 3]
    roles = re.search(r"static constexpr EpdChromaGridRole kRoles\[\] = \{[^}]*\};",
                      driver_text)
    if not roles:
        raise ValueError("fixture kRoles declaration not found in driver")
    roles_decl = roles.group(0).replace("kRoles", "kFixtureRoles")
    prefix = (audit.PROBE_PREFIX
              .replace('pal1_cal_v4_identity.inc', identity_name)
              .replace('mf1750_pal1_cal_v4', cpp_namespace))
    # The audit prefix's own package names may drift with revisions; the two
    # replacements above are authoritative only when they bite.
    prefix = re.sub(r'#include "\w+_identity\.inc"',
                    f'#include "{identity_name}"', prefix)
    prefix = re.sub(r'namespace ph = \w+;', f'namespace ph = {cpp_namespace};',
                    prefix)
    return prefix + roles_decl + "\n" + segment + frame_fn + audit.PROBE_MAIN


def check_package(package, work, compiler, environment):
    package = Path(package).resolve()
    generated = package / "generated"
    identity_path = next(generated.glob("*_identity.inc"))
    driver_path = next(generated.glob("*_driver.inc"))
    driver_text = driver_path.read_text(encoding="utf-8")
    identity_text = identity_path.read_text(encoding="utf-8")
    namespace = re.search(r"namespace (\w+) \{", identity_text).group(1)
    macro = re.search(r"#if defined\((MF1750_PALETTE_CAL_PAL1_V\d+_BUILD)\)",
                      driver_text).group(1)
    slots = int(re.search(r"kActions\[(\d+)\]", identity_text).group(1))
    roles = re.search(r"kRoles\[\] = \{([^}]*)\}", driver_text).group(1)
    role_names = [r.strip().split("::")[-1] for r in roles.split(",")]
    role_values = [audit.ROLE_ENUM_VALUE[r] for r in role_names]
    static_ok = all(0 < v < slots for v in role_values)
    probe = work / f"{package.name}-fixture-probe.cpp"
    probe.write_text(probe_source(driver_text, identity_path.name, namespace),
                     encoding="utf-8")
    exe = work / (package.name + "-fixture-probe.exe")
    args = [compiler, "/nologo", "/std:c++17", "/EHsc", "/utf-8",
            "/D_CRT_SECURE_NO_WARNINGS",
            "/I" + str(generated), "/I" + str(ROOT / "src"),
            # Same macro set as the package audit: the driver has macro-variant
            # sections, and probing without them compiles a different driver.
            "/DMF1750_ENABLE_CHROMA_GRID=1", "/D" + macro + "=1",
            "/DEPD_ENABLE_TEST_PATTERN=0", "/DMF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD=1",
            str(probe), "/Fe:" + str(exe),
            "/Fo:" + str(work / (package.name + "-fixture-probe.obj"))]
    result = subprocess.run(args, cwd=work, env=environment,
                            capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError("probe compile failed for " + package.name)
    run = subprocess.run([str(exe)], cwd=work, capture_output=True,
                         check=True)
    facts = {}
    for line in run.stdout.decode("utf-8").splitlines():
        key, _, value = line.partition("=")
        facts[key] = value
    return {
        "package": str(package),
        "identity_slots": slots,
        "fixture_roles": role_names,
        "static_role_bounds_ok": static_ok,
        "probe_facts": facts,
        "fixture_self_check_equivalent": facts.get("fixture_self_check_equivalent") == "1",
        "probe_source": base_firmware.bind(probe),
        "probe_binary": base_firmware.bind(exe),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--r1-package", type=Path,
                        default=ROOT / ".test-output/offline/PAL1_CAL_20260924_R1")
    parser.add_argument("--r2-package", type=Path,
                        default=ROOT / ".test-output/offline/PAL1_CAL_20260924_R2")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    compiler, environment, msvc = compiler_environment()
    if not msvc:
        raise RuntimeError("MSVC toolchain required")
    r1 = check_package(args.r1_package, out, compiler, environment)
    r2 = check_package(args.r2_package, out, compiler, environment)
    defect_reproduced = (
        not r1["static_role_bounds_ok"]
        and not r1["fixture_self_check_equivalent"]
        and r1["probe_facts"].get("fixture_role_2_index") == "2"
        and r1["probe_facts"].get("fixture_role_3_index") == "3")
    fix_verified = (r2["static_role_bounds_ok"]
                    and r2["fixture_self_check_equivalent"]
                    and r2["fixture_roles"] == ["Source"])
    report = {
        "kind": "mf1750-pal1-fixture-defect-repro-v1",
        "result": "PASS" if defect_reproduced and fix_verified else "FAIL_STOP",
        "hardware_accessed": False,
        "network_accessed": False,
        "root_cause": ("R1 identity compiles kActions[2] (slot 0 + one action) "
                       "while the frozen fixture loop validates roles "
                       "{Source,Mid,Target} and phValidateRole indexes "
                       "ph::kActions[(size_t)role] — Mid=2 and Target=3 read "
                       "out of bounds, so the boot-time histogram/identity "
                       "comparison can never pass and the firmware latches "
                       "compiled_fixture_self_check_failed before any ARM."),
        "r1_audit_miss": ("PAL1_CAL_NATIVE_20260924_R1 protocol fixture stubs "
                          "epdValidateCompiledChromaGridFixtures() and its "
                          "driver probe never indexed ph::kActions; this probe "
                          "closes the coverage hole"),
        "r1": r1,
        "r2": r2,
        "defect_reproduced_on_r1_package": defect_reproduced,
        "fix_verified_on_r2_package": fix_verified,
    }
    report["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(audit.pal1.canonical(report)).hexdigest(),
    }
    base_firmware.write_new(out / "fixture-defect-repro.json", report)
    print(json.dumps({"result": report["result"],
                      "defect_reproduced_on_r1_package": defect_reproduced,
                      "fix_verified_on_r2_package": fix_verified,
                      "report": str(out / "fixture-defect-repro.json")},
                     ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
