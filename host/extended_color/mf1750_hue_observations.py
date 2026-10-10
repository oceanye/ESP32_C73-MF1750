"""Offline observation records for MF1750 target-hue/lightness searches.

This module deliberately models a history recipe as a *candidate address*, not
as a colour.  Qualification is derived from explicit, reviewable evidence and
cannot be asserted by placing a ``qualified`` flag in an input document.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
DOCUMENT_KIND = "mf1750-target-hue-lightness-observation-template-v1"
VALIDATION_KIND = "mf1750-target-hue-lightness-observation-validation-v1"
SUMMARY_KIND = "mf1750-target-hue-lightness-observation-summary-v1"
CONTROLLERS = ("CS1", "CS2")
PERSISTENCE_POINTS = ("5s", "60s", "600s")
MINIMUM_INDEPENDENT_REPETITIONS = 3

_TOP_LEVEL_KEYS = {
    "schema_version",
    "kind",
    "offline_only",
    "hardware_accessed_by_tool",
    "source",
    "evidence_boundary",
    "qualification_requirements",
    "target_hue",
    "candidates",
    "template_id",
}
_CANDIDATE_KEYS = {
    "recipe",
    "candidate_only",
    "classification",
    "qualification_requested",
    "lightness_relationship",
    "local_hold",
    "factory_white_recovery",
    "observations",
}
_CLASSIFICATION_KEYS = {
    "observed_hue_id",
    "lightness_rank",
    "priority_mark",
    "notes",
}
_EVIDENCE_KEYS = {"status", "evidence_id", "notes"}
_OBSERVATION_KEYS = {
    "repetition",
    "run_id",
    "controllers",
    "controller_agreement",
}
_CONTROLLER_KEYS = {"target_repeat", "persistence"}
_TARGET_REPEAT_KEYS = {"before", "after", "stability"}
_SAMPLE_KEYS = {"uniformity", "color_word", "lab_d65_2deg"}
_PERSISTENCE_SAMPLE_KEYS = _SAMPLE_KEYS | {"retention"}
_AGREEMENT_KEYS = {"status", "evidence_note"}

_PRIORITY_MARKS = {"unreviewed", "watch", "priority", "reject"}
_EVIDENCE_STATUSES = {"pending", "pass", "fail"}
_UNIFORMITY_STATUSES = {"pending", "uniform", "nonuniform"}
_STABILITY_STATUSES = {"pending", "stable", "changed", "invalid"}
_AGREEMENT_STATUSES = {"pending", "pass", "fail"}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class HueObservationError(ValueError):
    """Raised when an observation document is ambiguous or malformed."""


def canonical_json(value: object) -> bytes:
    """Return deterministic UTF-8 JSON suitable for identities and reports."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise HueObservationError(f"document is not canonical JSON: {error}") from error


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _json_clone(value: object) -> Any:
    """Normalize tuples and other JSON sequences to their on-disk form."""

    return json.loads(canonical_json(value))


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HueObservationError(f"{label} must be an object")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise HueObservationError(
            f"{label} keys differ (missing={missing}, extra={extra})"
        )


def _optional_text(value: object, label: str, *, maximum: int = 200) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value != value.strip() or not value:
        raise HueObservationError(f"{label} must be null or trimmed non-empty text")
    if len(value) > maximum or any(ord(character) < 32 for character in value):
        raise HueObservationError(f"{label} is too long or contains control characters")
    return value


def _identifier(value: object, label: str, *, nullable: bool) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise HueObservationError(f"{label} must be a stable identifier")
    return value


def _lab(value: object, label: str) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or len(value) != 3
    ):
        raise HueObservationError(f"{label} must be null or [L*, a*, b*]")
    converted: list[float] = []
    for component in value:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            raise HueObservationError(f"{label} components must be numeric")
        number = float(component)
        if not math.isfinite(number):
            raise HueObservationError(f"{label} components must be finite")
        converted.append(number)
    if not 0.0 <= converted[0] <= 100.0:
        raise HueObservationError(f"{label} L* must be in [0, 100]")
    if any(not -200.0 <= component <= 200.0 for component in converted[1:]):
        raise HueObservationError(f"{label} a*/b* must be in [-200, 200]")
    return converted[0], converted[1], converted[2]


def _empty_sample() -> dict[str, object]:
    return {
        "uniformity": "pending",
        "color_word": None,
        "lab_d65_2deg": None,
    }


def _empty_controller_observation() -> dict[str, object]:
    return {
        "target_repeat": {
            "before": _empty_sample(),
            "after": _empty_sample(),
            "stability": "pending",
        },
        "persistence": {
            point: {**_empty_sample(), "retention": "pending"}
            for point in PERSISTENCE_POINTS
        },
    }


def _empty_repetition(repetition: int) -> dict[str, object]:
    return {
        "repetition": repetition,
        "run_id": None,
        "controllers": {
            controller: _empty_controller_observation() for controller in CONTROLLERS
        },
        "controller_agreement": {
            "status": "pending",
            "evidence_note": None,
        },
    }


def _empty_evidence() -> dict[str, object]:
    return {"status": "pending", "evidence_id": None, "notes": []}


def _source_hue(catalog: Mapping[str, Any], hue_id: str) -> Mapping[str, Any]:
    hues = catalog.get("target_hues")
    if not isinstance(hues, list):
        raise HueObservationError("target hue catalogue has no target_hues list")
    matching = [
        hue for hue in hues if isinstance(hue, Mapping) and hue.get("hue_id") == hue_id
    ]
    if len(matching) != 1:
        raise HueObservationError(f"target hue catalogue must contain one {hue_id!r}")
    return matching[0]


def _validate_source_inputs(
    catalog: Mapping[str, Any], blue_report: Mapping[str, Any]
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    if catalog.get("kind") != "mf1750-static-photo-target-hue-catalog":
        raise HueObservationError("target hue catalogue kind differs")
    if (
        catalog.get("offline_only") is not True
        or catalog.get("hardware_accessed") is not False
    ):
        raise HueObservationError("target hue catalogue crossed its offline boundary")
    _identifier(catalog.get("catalog_id"), "catalog_id", nullable=False)
    target_hue = _source_hue(catalog, "B")

    if blue_report.get("kind") != (
        "mf1750-target-hue-blue-brightness-history-v1-offline-identities"
    ):
        raise HueObservationError("Blue 64-recipe report kind differs")
    if (
        blue_report.get("offline_only") is not True
        or blue_report.get("hardware_accessed") is not False
    ):
        raise HueObservationError("Blue 64-recipe report crossed its offline boundary")
    _identifier(blue_report.get("contract_id"), "Blue contract_id", nullable=False)
    contract = _require_mapping(blue_report.get("contract"), "Blue contract")
    if contract.get("qualified_brightness_levels") != 0:
        raise HueObservationError("Blue source must contain zero qualified levels")
    if contract.get("spatial_dither") is not False:
        raise HueObservationError("Blue source must contain uniform, non-dither cells")
    recipes_raw = contract.get("recipes")
    if not isinstance(recipes_raw, list) or len(recipes_raw) != 64:
        raise HueObservationError("Blue source must contain exactly 64 recipes")
    recipes: list[Mapping[str, Any]] = []
    recipe_ids: list[str] = []
    for index, raw in enumerate(recipes_raw):
        recipe = _require_mapping(raw, f"Blue recipe {index}")
        recipe_id = _identifier(
            recipe.get("recipe_id"), f"Blue recipe {index} recipe_id", nullable=False
        )
        if recipe.get("spatial_dither") is not False:
            raise HueObservationError(f"Blue recipe {recipe_id} uses spatial dithering")
        repeats = recipe.get("controller_repeats")
        if not isinstance(repeats, list) or len(repeats) != 2:
            raise HueObservationError(
                f"Blue recipe {recipe_id} must repeat on two controllers"
            )
        recipes.append(recipe)
        recipe_ids.append(str(recipe_id))
    if len(set(recipe_ids)) != 64:
        raise HueObservationError("Blue recipe IDs must be unique")
    return target_hue, recipes


def build_observation_template(
    catalog: Mapping[str, Any], blue_report: Mapping[str, Any]
) -> dict[str, Any]:
    """Build a deterministic, blank observation document for all 64 recipes."""

    target_hue, recipes = _validate_source_inputs(catalog, blue_report)
    hue_ids = [
        hue["hue_id"]
        for hue in catalog["target_hues"]
        if isinstance(hue, Mapping) and isinstance(hue.get("hue_id"), str)
    ]
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": DOCUMENT_KIND,
        "offline_only": True,
        "hardware_accessed_by_tool": False,
        "source": {
            "catalog_id": catalog["catalog_id"],
            "catalog_kind": catalog["kind"],
            "available_hue_ids": hue_ids,
            "target_hue_id": "B",
            "blue_batch_id": "BLUE-BRIGHTNESS-64-V1",
            "blue_contract_id": blue_report["contract_id"],
            "blue_variant_key": blue_report["variant_key"],
            "blue_target_hue_id": blue_report["target_hue_id"],
            "recipe_count": len(recipes),
            "controllers": list(CONTROLLERS),
        },
        "evidence_boundary": {
            "candidate_recipe_count": len(recipes),
            "qualified_recipe_count_at_generation": 0,
            "qualified_unique_colour_count_at_generation": None,
            "history_recipes_are_not_unique_colours": True,
            "observer_color_words_are_not_measurements": True,
            "lab_is_optional_for_collection_but_required_for_qualification": True,
            "qualification_is_derived_not_operator_entered": True,
            "optical_distinctness_between_recipes_not_inferred": True,
        },
        "qualification_requirements": {
            "minimum_independent_repetitions": MINIMUM_INDEPENDENT_REPETITIONS,
            "required_controllers": list(CONTROLLERS),
            "required_persistence_points": list(PERSISTENCE_POINTS),
            "uniform_before_and_after_target_repeat": True,
            "stable_target_repeat": True,
            "controller_agreement_each_repetition": True,
            "measured_lab_each_sample": True,
            "lightness_relationship_evidence": True,
            "local_hold_evidence": True,
            "factory_white_recovery_evidence": True,
            "spatial_dither_forbidden": True,
        },
        "target_hue": _json_clone(target_hue),
        "candidates": [
            {
                "recipe": _json_clone(recipe),
                "candidate_only": True,
                "classification": {
                    "observed_hue_id": None,
                    "lightness_rank": None,
                    "priority_mark": "unreviewed",
                    "notes": [],
                },
                "qualification_requested": False,
                "lightness_relationship": _empty_evidence(),
                "local_hold": _empty_evidence(),
                "factory_white_recovery": _empty_evidence(),
                "observations": [
                    _empty_repetition(repetition)
                    for repetition in range(1, MINIMUM_INDEPENDENT_REPETITIONS + 1)
                ],
            }
            for recipe in recipes
        ],
    }
    return {**unsigned, "template_id": sha256_json(unsigned)}


def _validate_notes(value: object, label: str) -> None:
    if not isinstance(value, list) or len(value) > 50:
        raise HueObservationError(f"{label} must be a list of at most 50 notes")
    for index, note in enumerate(value):
        _optional_text(note, f"{label}[{index}]", maximum=500)


def _validate_evidence(value: object, label: str) -> Mapping[str, Any]:
    evidence = _require_mapping(value, label)
    _require_exact_keys(evidence, _EVIDENCE_KEYS, label)
    if evidence["status"] not in _EVIDENCE_STATUSES:
        raise HueObservationError(f"{label}.status differs")
    _identifier(evidence["evidence_id"], f"{label}.evidence_id", nullable=True)
    _validate_notes(evidence["notes"], f"{label}.notes")
    if evidence["status"] == "pass" and evidence["evidence_id"] is None:
        raise HueObservationError(f"{label} pass requires evidence_id")
    return evidence


def _validate_sample(
    value: object, label: str, *, persistence: bool
) -> Mapping[str, Any]:
    sample = _require_mapping(value, label)
    _require_exact_keys(
        sample,
        _PERSISTENCE_SAMPLE_KEYS if persistence else _SAMPLE_KEYS,
        label,
    )
    if sample["uniformity"] not in _UNIFORMITY_STATUSES:
        raise HueObservationError(f"{label}.uniformity differs")
    _optional_text(sample["color_word"], f"{label}.color_word")
    _lab(sample["lab_d65_2deg"], f"{label}.lab_d65_2deg")
    if persistence and sample["retention"] not in _STABILITY_STATUSES:
        raise HueObservationError(f"{label}.retention differs")
    return sample


def _validate_controller(value: object, label: str) -> Mapping[str, Any]:
    controller = _require_mapping(value, label)
    _require_exact_keys(controller, _CONTROLLER_KEYS, label)
    target_repeat = _require_mapping(
        controller["target_repeat"], f"{label}.target_repeat"
    )
    _require_exact_keys(target_repeat, _TARGET_REPEAT_KEYS, f"{label}.target_repeat")
    _validate_sample(
        target_repeat["before"], f"{label}.target_repeat.before", persistence=False
    )
    _validate_sample(
        target_repeat["after"], f"{label}.target_repeat.after", persistence=False
    )
    if target_repeat["stability"] not in _STABILITY_STATUSES:
        raise HueObservationError(f"{label}.target_repeat.stability differs")
    persistence = _require_mapping(controller["persistence"], f"{label}.persistence")
    _require_exact_keys(persistence, set(PERSISTENCE_POINTS), f"{label}.persistence")
    for point in PERSISTENCE_POINTS:
        _validate_sample(
            persistence[point], f"{label}.persistence.{point}", persistence=True
        )
    return controller


def _validate_observation(value: object, label: str) -> Mapping[str, Any]:
    observation = _require_mapping(value, label)
    _require_exact_keys(observation, _OBSERVATION_KEYS, label)
    if type(observation["repetition"]) is not int or observation["repetition"] <= 0:
        raise HueObservationError(f"{label}.repetition must be a positive integer")
    _identifier(observation["run_id"], f"{label}.run_id", nullable=True)
    controllers = _require_mapping(observation["controllers"], f"{label}.controllers")
    _require_exact_keys(controllers, set(CONTROLLERS), f"{label}.controllers")
    for controller in CONTROLLERS:
        _validate_controller(controllers[controller], f"{label}.{controller}")
    agreement = _require_mapping(
        observation["controller_agreement"], f"{label}.controller_agreement"
    )
    _require_exact_keys(agreement, _AGREEMENT_KEYS, f"{label}.controller_agreement")
    if agreement["status"] not in _AGREEMENT_STATUSES:
        raise HueObservationError(f"{label}.controller_agreement.status differs")
    _optional_text(
        agreement["evidence_note"],
        f"{label}.controller_agreement.evidence_note",
        maximum=500,
    )
    return observation


def _validate_candidate(
    value: object,
    expected: Mapping[str, Any],
    hue_ids: set[str],
    index: int,
) -> Mapping[str, Any]:
    label = f"candidate {index}"
    candidate = _require_mapping(value, label)
    _require_exact_keys(candidate, _CANDIDATE_KEYS, label)
    if candidate["recipe"] != expected["recipe"]:
        raise HueObservationError(f"{label} immutable recipe binding differs")
    if candidate["candidate_only"] is not True:
        raise HueObservationError(f"{label} must remain candidate_only=true")
    classification = _require_mapping(
        candidate["classification"], f"{label}.classification"
    )
    _require_exact_keys(classification, _CLASSIFICATION_KEYS, f"{label}.classification")
    hue_id = classification["observed_hue_id"]
    if hue_id is not None and hue_id not in hue_ids:
        raise HueObservationError(f"{label}.observed_hue_id is outside the catalogue")
    rank = classification["lightness_rank"]
    if rank is not None and (type(rank) is not int or rank <= 0):
        raise HueObservationError(f"{label}.lightness_rank must be null or positive")
    if classification["priority_mark"] not in _PRIORITY_MARKS:
        raise HueObservationError(f"{label}.priority_mark differs")
    _validate_notes(classification["notes"], f"{label}.classification.notes")
    if type(candidate["qualification_requested"]) is not bool:
        raise HueObservationError(f"{label}.qualification_requested must be boolean")
    for field in ("lightness_relationship", "local_hold", "factory_white_recovery"):
        _validate_evidence(candidate[field], f"{label}.{field}")
    observations = candidate["observations"]
    if not isinstance(observations, list) or len(observations) > 20:
        raise HueObservationError(f"{label}.observations must contain at most 20 runs")
    validated = [
        _validate_observation(item, f"{label}.observations[{position}]")
        for position, item in enumerate(observations)
    ]
    repetitions = [item["repetition"] for item in validated]
    if repetitions != list(range(1, len(repetitions) + 1)):
        raise HueObservationError(f"{label} repetition ordinals must be contiguous")
    return candidate


def _sample_complete(sample: Mapping[str, Any], *, persistence: bool) -> bool:
    return bool(
        sample["uniformity"] == "uniform"
        and sample["color_word"] is not None
        and sample["lab_d65_2deg"] is not None
        and (not persistence or sample["retention"] == "stable")
    )


def qualification_result(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Derive qualification; candidates cannot directly supply this result."""

    recipe = _require_mapping(candidate["recipe"], "candidate.recipe")
    recipe_id = str(recipe["recipe_id"])
    if candidate["qualification_requested"] is not True:
        return {
            "recipe_id": recipe_id,
            "qualified": False,
            "blockers": ["qualification_not_requested"],
        }

    blockers: list[str] = []
    classification = _require_mapping(candidate["classification"], "classification")
    if classification["observed_hue_id"] is None:
        blockers.append("observed_hue_unassigned")
    if classification["lightness_rank"] is None:
        blockers.append("lightness_rank_unassigned")
    if recipe.get("spatial_dither") is not False:
        blockers.append("spatial_dither_forbidden")
    for field in ("lightness_relationship", "local_hold", "factory_white_recovery"):
        evidence = _require_mapping(candidate[field], field)
        if evidence["status"] != "pass" or evidence["evidence_id"] is None:
            blockers.append(f"{field}_not_pass")

    observations = candidate["observations"]
    if len(observations) < MINIMUM_INDEPENDENT_REPETITIONS:
        blockers.append("fewer_than_three_independent_repetitions")
    run_ids = [item["run_id"] for item in observations]
    if any(run_id is None for run_id in run_ids):
        blockers.append("missing_run_id")
    non_null_run_ids = [run_id for run_id in run_ids if run_id is not None]
    if len(non_null_run_ids) != len(set(non_null_run_ids)):
        blockers.append("duplicate_run_id")

    for observation in observations:
        repetition = observation["repetition"]
        controllers = observation["controllers"]
        for controller_name in CONTROLLERS:
            controller = controllers[controller_name]
            target_repeat = controller["target_repeat"]
            if target_repeat["stability"] != "stable":
                blockers.append(
                    f"r{repetition}_{controller_name}_target_repeat_not_stable"
                )
            for stage in ("before", "after"):
                if not _sample_complete(target_repeat[stage], persistence=False):
                    blockers.append(
                        f"r{repetition}_{controller_name}_{stage}_sample_incomplete"
                    )
            for point in PERSISTENCE_POINTS:
                if not _sample_complete(
                    controller["persistence"][point], persistence=True
                ):
                    blockers.append(
                        f"r{repetition}_{controller_name}_{point}_persistence_incomplete"
                    )
        if observation["controller_agreement"]["status"] != "pass":
            blockers.append(f"r{repetition}_controller_agreement_not_pass")

    blockers = sorted(set(blockers))
    return {"recipe_id": recipe_id, "qualified": not blockers, "blockers": blockers}


def validate_observation_document(
    document: Mapping[str, Any], expected_template: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate structure/source binding and derive per-recipe qualification."""

    value = _require_mapping(document, "observation document")
    expected = _require_mapping(expected_template, "expected template")
    _require_exact_keys(value, _TOP_LEVEL_KEYS, "observation document")
    _require_exact_keys(expected, _TOP_LEVEL_KEYS, "expected template")
    for field in (
        "schema_version",
        "kind",
        "offline_only",
        "hardware_accessed_by_tool",
        "source",
        "evidence_boundary",
        "qualification_requirements",
        "target_hue",
        "template_id",
    ):
        if value[field] != expected[field]:
            raise HueObservationError(f"observation document {field} differs")
    if value["schema_version"] != SCHEMA_VERSION or value["kind"] != DOCUMENT_KIND:
        raise HueObservationError("observation document identity differs")
    if (
        value["offline_only"] is not True
        or value["hardware_accessed_by_tool"] is not False
    ):
        raise HueObservationError("observation document crossed its offline boundary")

    candidates = value["candidates"]
    expected_candidates = expected["candidates"]
    if not isinstance(candidates, list) or not isinstance(expected_candidates, list):
        raise HueObservationError("candidates must be a list")
    if len(candidates) != len(expected_candidates):
        raise HueObservationError("candidate count differs from the bound Blue pack")
    hue_ids = set(value["source"]["available_hue_ids"])
    validated = [
        _validate_candidate(candidate, expected_candidates[index], hue_ids, index)
        for index, candidate in enumerate(candidates)
    ]
    results = [qualification_result(candidate) for candidate in validated]
    qualified = [result["recipe_id"] for result in results if result["qualified"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": VALIDATION_KIND,
        "valid": True,
        "offline_only": True,
        "hardware_accessed_by_tool": False,
        "input_sha256": sha256_json(value),
        "template_id": value["template_id"],
        "candidate_recipe_count": len(validated),
        "qualification_requested_count": sum(
            candidate["qualification_requested"] is True for candidate in validated
        ),
        "qualified_recipe_count": len(qualified),
        "qualified_unique_colour_count": None,
        "qualified_recipe_ids": qualified,
        "history_recipes_are_not_unique_colours": True,
        "qualification_results": results,
    }


def summarize_observation_document(
    document: Mapping[str, Any], expected_template: Mapping[str, Any]
) -> dict[str, Any]:
    """Produce a compact deterministic collection/qualification summary."""

    validation = validate_observation_document(document, expected_template)
    candidates = document["candidates"]
    hue_order = list(document["source"]["available_hue_ids"])
    hue_counts: Counter[str] = Counter()
    priority_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    priority_recipe_ids: list[str] = []
    observed_recipe_count = 0
    lab_sample_count = 0
    total_sample_slots = 0

    for candidate in candidates:
        recipe_id = candidate["recipe"]["recipe_id"]
        classification = candidate["classification"]
        hue_counts[classification["observed_hue_id"] or "unassigned"] += 1
        priority_counts[classification["priority_mark"]] += 1
        if classification["priority_mark"] == "priority":
            priority_recipe_ids.append(recipe_id)
        if any(
            observation["run_id"] is not None
            for observation in candidate["observations"]
        ):
            observed_recipe_count += 1
        for observation in candidate["observations"]:
            for controller in CONTROLLERS:
                controller_record = observation["controllers"][controller]
                samples = [
                    controller_record["target_repeat"]["before"],
                    controller_record["target_repeat"]["after"],
                    *[
                        controller_record["persistence"][point]
                        for point in PERSISTENCE_POINTS
                    ],
                ]
                total_sample_slots += len(samples)
                lab_sample_count += sum(
                    sample["lab_d65_2deg"] is not None for sample in samples
                )
    for result in validation["qualification_results"]:
        blocker_counts.update(result["blockers"])

    ordered_hue_counts = {
        hue_id: hue_counts[hue_id] for hue_id in [*hue_order, "unassigned"]
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": SUMMARY_KIND,
        "valid": True,
        "offline_only": True,
        "hardware_accessed_by_tool": False,
        "input_sha256": validation["input_sha256"],
        "template_id": validation["template_id"],
        "candidate_recipe_count": validation["candidate_recipe_count"],
        "observed_recipe_count": observed_recipe_count,
        "qualification_requested_count": validation["qualification_requested_count"],
        "qualified_recipe_count": validation["qualified_recipe_count"],
        "qualified_unique_colour_count": None,
        "history_recipes_are_not_unique_colours": True,
        "qualified_recipe_ids": validation["qualified_recipe_ids"],
        "priority_recipe_ids": priority_recipe_ids,
        "hue_assignment_counts": ordered_hue_counts,
        "priority_mark_counts": {
            mark: priority_counts[mark] for mark in sorted(_PRIORITY_MARKS)
        },
        "lab_coverage": {
            "populated_sample_count": lab_sample_count,
            "total_sample_slots": total_sample_slots,
        },
        "qualification_blocker_counts": dict(sorted(blocker_counts.items())),
    }
