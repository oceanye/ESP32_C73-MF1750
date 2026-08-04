from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools import validate_ci_reports


def _valid_host_report() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "mf1750_host_unittest_report",
        "passed": True,
        "hardware_tested": False,
        "tests_run": 3,
        "tests_executed": 2,
        "suite_empty": False,
        "all_tests_skipped": False,
        "failures": 0,
        "errors": 0,
        "skipped": 1,
        "unexpected_successes": 0,
    }


def _valid_repository_report() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "mf1750-repository-contract-report",
        "passed": True,
        "hardware_tested": False,
        "checks": [
            {"name": "example", "passed": True, "errors": [], "warnings": []}
        ],
    }


class ValidateCiReportsTests(unittest.TestCase):
    def _write_reports(
        self,
        root: Path,
        *,
        host: object | None = None,
        repository: object | None = None,
    ) -> tuple[Path, Path]:
        host_path = root / "host.json"
        repository_path = root / "repository.json"
        host_path.write_text(
            json.dumps(_valid_host_report() if host is None else host),
            encoding="utf-8",
        )
        repository_path.write_text(
            json.dumps(
                _valid_repository_report() if repository is None else repository
            ),
            encoding="utf-8",
        )
        return host_path, repository_path

    def test_valid_positive_reports_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            host_path, repository_path = self._write_reports(Path(temporary))
            errors = validate_ci_reports.validate_report_files(
                host_path, repository_path
            )
        self.assertEqual(errors, [])

    def test_zero_or_all_skipped_host_tests_fail(self) -> None:
        for host in (
            {
                **_valid_host_report(),
                "tests_run": 0,
                "tests_executed": 0,
                "skipped": 0,
                "suite_empty": True,
                "passed": False,
            },
            {
                **_valid_host_report(),
                "tests_run": 2,
                "tests_executed": 0,
                "skipped": 2,
                "all_tests_skipped": True,
                "passed": False,
            },
        ):
            with self.subTest(host=host):
                errors = validate_ci_reports.validate_host_report(host)
                self.assertTrue(errors)

    def test_wrong_host_identity_or_false_result_fails(self) -> None:
        host = _valid_host_report()
        host["kind"] = "not-the-host-report"
        host["passed"] = False
        errors = validate_ci_reports.validate_host_report(host)
        self.assertIn("host: unexpected report kind", errors)
        self.assertIn("host: passed must be true", errors)

    def test_boolean_schema_versions_are_rejected(self) -> None:
        host = _valid_host_report()
        host["schema_version"] = True
        repository = _valid_repository_report()
        repository["schema_version"] = True
        self.assertIn(
            "host: unexpected schema_version",
            validate_ci_reports.validate_host_report(host),
        )
        self.assertIn(
            "repository: unexpected schema_version",
            validate_ci_reports.validate_repository_report(repository),
        )

    def test_failed_repository_check_fails(self) -> None:
        repository = _valid_repository_report()
        repository["checks"] = [
            {"name": "broken", "passed": False, "errors": ["failure"]}
        ]
        errors = validate_ci_reports.validate_repository_report(repository)
        self.assertTrue(any("checks[0].passed" in error for error in errors))
        self.assertTrue(any("checks[0].errors" in error for error in errors))

    def test_missing_or_malformed_report_fails_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            host_path = root / "missing.json"
            repository_path = root / "repository.json"
            repository_path.write_text("not json", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                status = validate_ci_reports.main(
                    [
                        "--host-report",
                        str(host_path),
                        "--repository-report",
                        str(repository_path),
                    ]
                )
        self.assertEqual(status, 1)


if __name__ == "__main__":
    unittest.main()
