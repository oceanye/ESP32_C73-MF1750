#!/usr/bin/env python3
"""Fail closed when deterministic KiCad routing UUID seeds drift or collide."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


HARDWARE = Path(__file__).resolve().parent
REGISTRY = HARDWARE / "mf1750_wroom_b3_power_tf" / "ROUTING_UUID_SEEDS.json"
SEED_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Za-z_][A-Za-z0-9_]*\.)?"
    r"(?:ROUTING_UUID_SEED|ROUTE_UUID_SEED)\s*=\s*"
    r"(0x[0-9A-Fa-f]+|[0-9]+)"
)


def parse_seed(raw: str) -> int:
    return int(raw, 0)


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assignments = registry["assignments"]
    collisions = registry.get("known_collisions", [])
    failures: list[str] = []

    assignment_by_owner: dict[str, dict[str, object]] = {}
    owner_by_seed: dict[int, str] = {}
    for record in assignments:
        owner = str(record["owner"])
        seed = int(record["seed_decimal"])
        if owner in assignment_by_owner:
            failures.append(f"duplicate assignment owner: {owner}")
        if seed in owner_by_seed:
            failures.append(
                f"duplicate assigned seed {seed}: {owner_by_seed[seed]} and {owner}"
            )
        assignment_by_owner[owner] = record
        owner_by_seed[seed] = owner

    collision_by_rejected_owner: dict[str, dict[str, object]] = {}
    for record in collisions:
        rejected = str(record["rejected_owner"])
        occupied = str(record["occupied_owner"])
        seed = int(record["seed_decimal"])
        if rejected in collision_by_rejected_owner:
            failures.append(f"duplicate known-collision owner: {rejected}")
        collision_by_rejected_owner[rejected] = record
        if owner_by_seed.get(seed) != occupied:
            failures.append(
                f"known collision seed {seed} is not assigned to {occupied}"
            )

    discovered: dict[str, list[int]] = {}
    for script in sorted(HARDWARE.glob("*.py")):
        values = sorted(
            {
                parse_seed(match.group(1))
                for match in SEED_PATTERN.finditer(
                    script.read_text(encoding="utf-8", errors="strict")
                )
            }
        )
        if values:
            discovered[script.name] = values
        if len(values) > 1:
            failures.append(f"multiple literal routing seeds in {script.name}: {values}")

    for owner, values in discovered.items():
        for seed in values:
            assignment = assignment_by_owner.get(owner)
            collision = collision_by_rejected_owner.get(owner)
            if assignment and int(assignment["seed_decimal"]) == seed:
                continue
            if collision and int(collision["seed_decimal"]) == seed:
                continue
            failures.append(f"unregistered literal seed: {owner}={seed}")

    for owner, assignment in assignment_by_owner.items():
        status = str(assignment["status"])
        expected = int(assignment["seed_decimal"])
        actual = discovered.get(owner)
        if actual == [expected]:
            continue
        if status == "reserved_for_candidate" and actual is None:
            continue
        failures.append(
            f"registered owner seed drift/missing: {owner}, expected={expected}, "
            f"actual={actual}, status={status}"
        )

    for owner, collision in collision_by_rejected_owner.items():
        expected = int(collision["seed_decimal"])
        if discovered.get(owner) != [expected]:
            failures.append(
                f"known-collision evidence drift: {owner}, expected={expected}, "
                f"actual={discovered.get(owner)}"
            )

    result = {
        "schema": 1,
        "registry": str(REGISTRY),
        "registered_unique_seeds": len(owner_by_seed),
        "known_collisions": len(collisions),
        "discovered_seeded_scripts": len(discovered),
        "passed": not failures,
        "failures": failures,
        "discovered": discovered,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
