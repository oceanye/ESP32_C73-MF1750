from __future__ import annotations

import ast
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class TransitionOptimizerRepositoryContractTests(unittest.TestCase):
    def test_sources_tests_schema_and_handoff_exist(self) -> None:
        required = (
            "host/transition_optimizer/__init__.py",
            "host/transition_optimizer/optimizer.py",
            "host/transition_optimizer/README.md",
            "tests/test_transition_optimizer.py",
            "tools/mf1750_transition_optimize.py",
            "schemas/extended_color/transition_profile.schema.json",
            "docs/C3_TRANSITION_OPTIMIZER_OFFLINE_HANDOFF_2026-08-08.md",
        )
        for relative in required:
            self.assertTrue((REPO_ROOT / relative).is_file(), relative)

    def test_host_package_has_no_network_device_or_runner_import(self) -> None:
        forbidden_roots = {
            "http",
            "requests",
            "serial",
            "socket",
            "subprocess",
            "urllib",
        }
        paths = list((REPO_ROOT / "host/transition_optimizer").glob("*.py"))
        paths.append(REPO_ROOT / "tools/mf1750_transition_optimize.py")
        for path in paths:
            is_host_package = path.parent == REPO_ROOT / "host/transition_optimizer"
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = {alias.name.split(".", 1)[0] for alias in node.names}
                    self.assertTrue(forbidden_roots.isdisjoint(roots), (path, roots))
                elif isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".", 1)[0]
                    self.assertNotIn(root, forbidden_roots, (path, root))
                    if is_host_package:
                        self.assertNotEqual(root, "tools", (path, root))

    def test_handoff_forbids_busy_speed_and_hardware_qualification_claims(self) -> None:
        handoff = (
            REPO_ROOT / "docs/C3_TRANSITION_OPTIMIZER_OFFLINE_HANDOFF_2026-08-08.md"
        ).read_text(encoding="utf-8")
        for statement in (
            "busy_time_reduction_claim_allowed=false",
            "optimizer_output_hardware_qualified",
            "selection=null",
            "TransitionInputBinding",
            "15/15 PASS",
        ):
            self.assertIn(statement, handoff)

    def test_master_todo_no_longer_calls_optimizer_unstarted(self) -> None:
        todo = (REPO_ROOT / "docs/TODO_MULTI_AI_HANDOFF_PLAN_2026-08-04.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("完整优化器未开始", todo)
        self.assertIn("C3_TRANSITION_OPTIMIZER_OFFLINE_HANDOFF_2026-08-08.md", todo)


if __name__ == "__main__":
    unittest.main()
