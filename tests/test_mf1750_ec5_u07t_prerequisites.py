from __future__ import annotations

from pathlib import Path

import pytest

from tools import mf1750_ec5_u07t_identity as identity
from tools import mf1750_ec5_u07t_prerequisites as prereq


def test_formal_claim_absence_records_exact_formal_action(tmp_path: Path) -> None:
    report = prereq.formal_u07_claim_absence(tmp_path)
    assert report["registry_id"] == identity.FORMAL_CLAIM_REGISTRY_ID
    assert report["action_id"] == identity.FORMAL_U07_ACTION_ID
    assert report["exists"] is False
    assert report["formal_action_consumed"] is False


def test_formal_claim_presence_fails_closed(tmp_path: Path) -> None:
    (tmp_path / f"{identity.FORMAL_U07_ACTION_ID}.json").write_text("{}")
    with pytest.raises(prereq.U07TPrerequisiteError, match="already claimed"):
        prereq.formal_u07_claim_absence(tmp_path)


def test_formal_and_technical_registries_must_differ(tmp_path: Path) -> None:
    with pytest.raises(prereq.U07TPrerequisiteError, match="must differ"):
        prereq.distinct_claim_registries(tmp_path, tmp_path)


def test_distinct_claim_registries_accept_separate_paths(tmp_path: Path) -> None:
    formal = tmp_path / "formal"
    technical = tmp_path / "technical"
    formal.mkdir()
    observed_formal, observed_technical = prereq.distinct_claim_registries(
        formal, technical
    )
    assert observed_formal == formal.resolve()
    assert observed_technical == technical
