#!/usr/bin/env python3
"""Run repository host tests and emit a machine-readable unittest report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
import traceback
from typing import Any, Sequence, TextIO
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIRECTORY = REPO_ROOT / "tests"
PRODUCTION_DIRECTORY = (
    REPO_ROOT / "hardware" / "mf1750_production_v1" / "production"
).resolve()
REPORT_SCHEMA_VERSION = 1
REPORT_KIND = "mf1750_host_unittest_report"

# ``python tools/run_host_tests.py`` otherwise puts only tools/ at sys.path[0].
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class OutputSafetyError(ValueError):
    """Raised when the requested report target is unsafe or ambiguous."""


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _existing_identity(path: Path) -> tuple[int, int, int]:
    metadata = path.stat()
    return (metadata.st_dev, metadata.st_ino, metadata.st_nlink)


def validate_output_path(raw_path: str | os.PathLike[str], *, force: bool) -> Path:
    """Resolve and validate an output target before any tests are executed."""

    lexical_path = Path(raw_path).expanduser()
    if not lexical_path.is_absolute():
        lexical_path = Path.cwd() / lexical_path

    # Resolving an existing final-component symlink and replacing the result would
    # overwrite its target. Reject it before resolve(), including broken links.
    if lexical_path.is_symlink():
        raise OutputSafetyError("report output must not be a symbolic link")

    output_path = lexical_path.resolve(strict=False)
    if output_path == PRODUCTION_DIRECTORY or _is_relative_to(
        output_path, PRODUCTION_DIRECTORY
    ):
        raise OutputSafetyError(
            "report output must not be inside the frozen production directory"
        )

    if output_path.exists():
        if not output_path.is_file():
            raise OutputSafetyError("report output exists and is not a regular file")
        metadata = output_path.stat()
        if metadata.st_nlink > 1:
            raise OutputSafetyError("report output must not be a hard-link alias")
        if not force:
            raise OutputSafetyError(
                "report output already exists; pass --force to replace it"
            )

    return output_path


def _test_identifier(test: object) -> str:
    identifier = getattr(test, "id", None)
    if callable(identifier):
        try:
            value = identifier()
        except Exception:  # pragma: no cover - defensive for third-party tests
            value = None
        if isinstance(value, str) and value:
            return value
    return str(test)


def _problem_records(entries: Sequence[tuple[object, str]]) -> list[dict[str, str]]:
    return [
        {"test": _test_identifier(test), "traceback": details}
        for test, details in entries
    ]


def _skip_records(entries: Sequence[tuple[object, str]]) -> list[dict[str, str]]:
    return [
        {"test": _test_identifier(test), "reason": reason}
        for test, reason in entries
    ]


def build_report(
    result: unittest.TestResult,
    *,
    duration_seconds: float,
) -> dict[str, Any]:
    """Serialize a unittest result without capturing process environment data."""

    failures = _problem_records(result.failures)
    errors = _problem_records(result.errors)
    skipped = _skip_records(getattr(result, "skipped", []))
    expected_failures = _problem_records(
        getattr(result, "expectedFailures", [])
    )
    unexpected_successes = [
        _test_identifier(test)
        for test in getattr(result, "unexpectedSuccesses", [])
    ]
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "passed": result.wasSuccessful(),
        "hardware_tested": False,
        "tests_run": result.testsRun,
        "failures": len(failures),
        "errors": len(errors),
        "skipped": len(skipped),
        "expected_failures": len(expected_failures),
        "unexpected_successes": len(unexpected_successes),
        "failure_details": failures,
        "error_details": errors,
        "skip_details": skipped,
        "expected_failure_details": expected_failures,
        "unexpected_success_details": unexpected_successes,
        "duration_seconds": round(max(0.0, duration_seconds), 6),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "runner": {
            "framework": "unittest",
            "discovery_start": "tests",
            "pattern": "test*.py",
            "verbosity": 2,
        },
    }


def build_runner_error_report(error: BaseException, *, duration_seconds: float) -> dict[str, Any]:
    """Return the same schema when discovery or the runner itself crashes."""

    report = build_report(unittest.TestResult(), duration_seconds=duration_seconds)
    report["passed"] = False
    report["errors"] = 1
    report["error_details"] = [
        {
            "test": "host_test_runner",
            "traceback": "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ),
        }
    ]
    return report


def discover_suite() -> unittest.TestSuite:
    loader = unittest.defaultTestLoader
    return loader.discover(
        start_dir=str(TESTS_DIRECTORY),
        pattern="test*.py",
        top_level_dir=str(REPO_ROOT),
    )


def run_suite(
    suite: unittest.TestSuite,
    *,
    stream: TextIO | None = None,
) -> tuple[unittest.TestResult, float]:
    started = time.perf_counter()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)
    result = runner.run(suite)
    return result, time.perf_counter() - started


def _atomic_write_report(
    output_path: Path,
    report: dict[str, Any],
    *,
    force: bool,
) -> None:
    """Write complete JSON in one filesystem-visible operation."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Revalidate after directory creation to narrow path/symlink races.
    checked_path = validate_output_path(output_path, force=force)
    if checked_path != output_path:
        raise OutputSafetyError("report output changed while it was being prepared")

    previous_identity = (
        _existing_identity(output_path) if output_path.exists() else None
    )
    payload = (
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())

        temporary_path = Path(temporary_name)
        if previous_identity is None:
            # link() supplies atomic no-clobber semantics. The temporary name and
            # final name briefly reference the same complete inode.
            try:
                os.link(temporary_path, output_path)
            except FileExistsError as error:
                raise OutputSafetyError(
                    "report output appeared during write; refusing to replace it"
                ) from error
        else:
            if output_path.is_symlink() or not output_path.is_file():
                raise OutputSafetyError("report output changed during write")
            if _existing_identity(output_path) != previous_identity:
                raise OutputSafetyError("report output changed during write")
            os.replace(temporary_path, output_path)
            temporary_name = None
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run host unittest discovery and write a JSON result report."
    )
    parser.add_argument(
        "--output",
        default="host-test-report.json",
        help="JSON report path (default: host-test-report.json)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing ordinary report file",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        output_path = validate_output_path(args.output, force=args.force)
    except (OSError, OutputSafetyError) as error:
        print(f"host test report path error: {error}", file=sys.stderr)
        return 2

    started = time.perf_counter()
    runner_failed = False
    try:
        result, duration_seconds = run_suite(discover_suite())
        report = build_report(result, duration_seconds=duration_seconds)
    except Exception as error:  # preserve an artifact for CI infrastructure errors
        runner_failed = True
        duration_seconds = time.perf_counter() - started
        traceback.print_exc()
        report = build_runner_error_report(error, duration_seconds=duration_seconds)

    try:
        _atomic_write_report(output_path, report, force=args.force)
    except (OSError, OutputSafetyError) as error:
        print(f"host test report write error: {error}", file=sys.stderr)
        return 2

    print(f"host test report: {output_path}")
    if runner_failed:
        return 2
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
