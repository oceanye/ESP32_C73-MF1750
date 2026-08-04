#!/usr/bin/env python3
"""Fail closed unless both CI machine reports contain positive gate evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


HOST_REPORT_KIND = "mf1750_host_unittest_report"
REPOSITORY_REPORT_KIND = "mf1750-repository-contract-report"
REPORT_SCHEMA_VERSION = 1


def _plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _load_report(path: Path, label: str) -> tuple[Mapping[str, Any] | None, list[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return None, [f"{label}: cannot read valid JSON from {path}: {error}"]
    if not isinstance(payload, dict):
        return None, [f"{label}: top-level JSON value must be an object"]
    return payload, []


def validate_host_report(report: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    schema_version = report.get("schema_version")
    if not _plain_int(schema_version) or schema_version != REPORT_SCHEMA_VERSION:
        errors.append("host: unexpected schema_version")
    if report.get("kind") != HOST_REPORT_KIND:
        errors.append("host: unexpected report kind")
    if report.get("hardware_tested") is not False:
        errors.append("host: hardware_tested must be false")

    tests_run = report.get("tests_run")
    tests_executed = report.get("tests_executed")
    skipped = report.get("skipped")
    if not _plain_int(tests_run) or tests_run < 1:
        errors.append("host: tests_run must be a positive integer")
    if not _plain_int(tests_executed) or tests_executed < 1:
        errors.append("host: tests_executed must be a positive integer")
    if not _plain_int(skipped) or skipped < 0:
        errors.append("host: skipped must be a non-negative integer")
    if all(_plain_int(value) for value in (tests_run, tests_executed, skipped)):
        if tests_executed != tests_run - skipped:
            errors.append("host: tests_executed must equal tests_run - skipped")

    for field in ("failures", "errors", "unexpected_successes"):
        value = report.get(field)
        if not _plain_int(value) or value != 0:
            errors.append(f"host: {field} must be integer zero")
    if report.get("suite_empty") is not False:
        errors.append("host: suite_empty must be false")
    if report.get("all_tests_skipped") is not False:
        errors.append("host: all_tests_skipped must be false")
    if report.get("passed") is not True:
        errors.append("host: passed must be true")
    return errors


def validate_repository_report(report: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    schema_version = report.get("schema_version")
    if not _plain_int(schema_version) or schema_version != REPORT_SCHEMA_VERSION:
        errors.append("repository: unexpected schema_version")
    if report.get("kind") != REPOSITORY_REPORT_KIND:
        errors.append("repository: unexpected report kind")
    if report.get("hardware_tested") is not False:
        errors.append("repository: hardware_tested must be false")
    if report.get("passed") is not True:
        errors.append("repository: passed must be true")

    checks = report.get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append("repository: checks must be a non-empty array")
        return errors
    for index, check in enumerate(checks):
        prefix = f"repository: checks[{index}]"
        if not isinstance(check, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if check.get("passed") is not True:
            errors.append(f"{prefix}.passed must be true")
        check_errors = check.get("errors")
        if not isinstance(check_errors, list) or check_errors:
            errors.append(f"{prefix}.errors must be an empty array")
    return errors


def validate_report_files(host_path: Path, repository_path: Path) -> list[str]:
    errors: list[str] = []
    host_report, load_errors = _load_report(host_path, "host")
    errors.extend(load_errors)
    if host_report is not None:
        errors.extend(validate_host_report(host_report))

    repository_report, load_errors = _load_report(repository_path, "repository")
    errors.extend(load_errors)
    if repository_report is not None:
        errors.extend(validate_repository_report(repository_report))
    return errors


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate positive evidence in CI host and repository reports."
    )
    parser.add_argument(
        "--host-report",
        type=Path,
        default=Path("host-test-report.json"),
    )
    parser.add_argument(
        "--repository-report",
        type=Path,
        default=Path("repo-contract-report.json"),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    errors = validate_report_files(args.host_report, args.repository_report)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("CI machine reports: valid positive host/repository evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
