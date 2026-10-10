#!/usr/bin/env python3
"""Build or validate the non-materializable 12-action waveform campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.runtime_waveform import campaign  # noqa: E402


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", allow_abbrev=False)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--created-at", required=True)
    validate = sub.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--bundle", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "build":
            report = campaign.write_placeholder_bundle(
                args.output, created_at=args.created_at
            )
        else:
            report = campaign.validate_placeholder_bundle_directory(args.bundle)
    except (campaign.PlaceholderCampaignError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
