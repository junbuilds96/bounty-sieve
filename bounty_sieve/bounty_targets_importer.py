"""Local import helpers for arkadiyt/bounty-targets-data style JSON dumps."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bounty_sieve.opportunities import OpportunityValidationError, normalize_opportunities


SUPPORTED_PLATFORMS = {"hackerone", "bugcrowd"}
SUMMARY_LIMIT = 320


class BountyTargetsDataImportError(ValueError):
    """Raised when a local bounty-targets-data dump cannot be imported safely."""


def import_bounty_targets_data(path: str | Path, platform: str) -> list[dict[str, Any]]:
    """Load a local bounty-targets-data JSON dump and normalize it."""
    normalized_platform = _normalize_platform(platform)
    payload = _read_local_json(path)
    programs = _extract_programs(payload)

    if normalized_platform == "hackerone":
        opportunities = _hackerone_programs_to_opportunities(programs)
    else:
        opportunities = _bugcrowd_programs_to_opportunities(programs)
    try:
        return normalize_opportunities(opportunities)
    except OpportunityValidationError as exc:
        raise BountyTargetsDataImportError(str(exc)) from exc


def _normalize_platform(platform: str) -> str:
    normalized = platform.strip().lower()
    if normalized not in SUPPORTED_PLATFORMS:
        allowed = ", ".join(sorted(SUPPORTED_PLATFORMS))
        raise BountyTargetsDataImportError(f"--platform must be one of: {allowed}")
    return normalized


def _read_local_json(path: str | Path) -> Any:
    path_text = str(path)
    parsed = urlparse(path_text)
    if path_text == "-" or parsed.scheme or parsed.netloc:
        raise BountyTargetsDataImportError("--input must be a local JSON file path")
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise BountyTargetsDataImportError(f"input file not found: {path}") from exc
    except OSError as exc:
        raise BountyTargetsDataImportError(f"could not read input file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BountyTargetsDataImportError(f"input file is not valid JSON: {exc}") from exc


def _extract_programs(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        programs = payload
    elif isinstance(payload, dict):
        candidates = [
            payload.get("programs"),
            payload.get("data"),
            payload.get("results"),
        ]
        programs = next((item for item in candidates if isinstance(item, list)), None)
        if programs is None:
            raise BountyTargetsDataImportError(
                'top-level JSON must be a list or an object with a "programs", "data", or "results" list'
            )
    else:
        raise BountyTargetsDataImportError("top-level JSON must be a list or object")

    for index, program in enumerate(programs):
        if not isinstance(program, dict):
            raise BountyTargetsDataImportError(f"programs[{index}] must be an object")
    return programs


def _hackerone_programs_to_opportunities(programs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    opportunities = []
    seen_ids: Counter[str] = Counter()
    for index, program in enumerate(programs):
        name = _string(program.get("name")) or _string(program.get("handle")) or "Unnamed HackerOne program"
        handle = _string(program.get("handle"))
        base_id = _slug(handle or name)
        opportunity_id = _dedupe_id(f"hackerone-{base_id}", seen_ids, index)
        targets = _target_groups(program)
        in_scope = targets["in_scope"]
        out_of_scope = targets["out_of_scope"]
        target_types = _hackerone_target_types(in_scope)
        offers_bounties = program.get("offers_bounties") is True
        offers_swag = program.get("offers_swag") is True
        labels = _labels(
            [
                "bounty-targets-data",
                "hackerone",
                "offers-bounties" if offers_bounties else None,
                "offers-swag" if offers_swag else None,
                _submission_state_label(program.get("submission_state")),
                "managed" if program.get("managed_program") is True else None,
                *target_types.keys(),
            ]
        )

        opportunities.append(
            {
                "id": opportunity_id,
                "title": f"HackerOne program: {name}",
                "url": _string(program.get("url")),
                "platform": "hackerone",
                "repo": None,
                "source": "bounty-targets-data",
                "labels": labels,
                "summary": _truncate(
                    " ".join(
                        [
                            f"Public HackerOne bounty-targets-data program dump for {name}.",
                            f"In-scope targets: {len(in_scope)}.",
                            f"Out-of-scope targets: {len(out_of_scope)}.",
                            f"Paid bounties: {'yes' if offers_bounties else 'no'}.",
                            _submission_state_sentence(program.get("submission_state")),
                        ]
                    ),
                    SUMMARY_LIMIT,
                ),
                "reward": {
                    "amount": 0,
                    "currency": "USD",
                    "type": "conditional" if offers_bounties else "unknown",
                },
                "signals": _signals_from_target_counts(len(in_scope), target_types),
                "metadata": {
                    "bounty_targets_data": {
                        "platform": "hackerone",
                        "program_id": _safe_int(program.get("id")),
                        "handle": handle,
                        "website": _string(program.get("website")),
                        "submission_state": _string(program.get("submission_state")),
                        "managed_program": _safe_bool(program.get("managed_program")),
                        "offers_bounties": offers_bounties,
                        "offers_swag": offers_swag,
                        "allows_bounty_splitting": _safe_bool(
                            program.get("allows_bounty_splitting")
                        ),
                        "response_efficiency_percentage": _safe_number(
                            program.get("response_efficiency_percentage")
                        ),
                        "in_scope_count": len(in_scope),
                        "out_of_scope_count": len(out_of_scope),
                        "in_scope_bounty_eligible_count": _hackerone_bounty_eligible_count(
                            in_scope
                        ),
                        "target_types": dict(target_types),
                    }
                },
            }
        )
    return opportunities


def _bugcrowd_programs_to_opportunities(programs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    opportunities = []
    seen_ids: Counter[str] = Counter()
    for index, program in enumerate(programs):
        name = _string(program.get("name")) or "Unnamed Bugcrowd program"
        url = _string(program.get("url"))
        base_id = _slug(_url_tail(url) or name)
        opportunity_id = _dedupe_id(f"bugcrowd-{base_id}", seen_ids, index)
        targets = _target_groups(program)
        in_scope = targets["in_scope"]
        out_of_scope = targets["out_of_scope"]
        target_types = _bugcrowd_target_types(in_scope)
        max_payout = _safe_int(program.get("max_payout")) or 0
        safe_harbor = _string(program.get("safe_harbor"))
        labels = _labels(
            [
                "bounty-targets-data",
                "bugcrowd",
                "managed" if program.get("managed_by_bugcrowd") is True else None,
                "allows-disclosure" if program.get("allows_disclosure") is True else None,
                f"safe-harbor-{_slug(safe_harbor)}" if safe_harbor else None,
                *target_types.keys(),
            ]
        )

        opportunities.append(
            {
                "id": opportunity_id,
                "title": f"Bugcrowd program: {name}",
                "url": url,
                "platform": "bugcrowd",
                "repo": None,
                "source": "bounty-targets-data",
                "labels": labels,
                "summary": _truncate(
                    " ".join(
                        [
                            f"Public Bugcrowd bounty-targets-data program dump for {name}.",
                            f"In-scope targets: {len(in_scope)}.",
                            f"Out-of-scope targets: {len(out_of_scope)}.",
                            f"Max listed payout: ${max_payout}.",
                            f"Safe harbor: {safe_harbor or 'unknown'}.",
                        ]
                    ),
                    SUMMARY_LIMIT,
                ),
                "reward": {
                    "amount": max_payout,
                    "currency": "USD",
                    "type": "estimated" if max_payout > 0 else "unknown",
                },
                "signals": _signals_from_target_counts(len(in_scope), target_types),
                "metadata": {
                    "bounty_targets_data": {
                        "platform": "bugcrowd",
                        "allows_disclosure": _safe_bool(program.get("allows_disclosure")),
                        "managed_by_bugcrowd": _safe_bool(program.get("managed_by_bugcrowd")),
                        "safe_harbor": safe_harbor,
                        "max_payout": max_payout,
                        "in_scope_count": len(in_scope),
                        "out_of_scope_count": len(out_of_scope),
                        "target_types": dict(target_types),
                    }
                },
            }
        )
    return opportunities


def _target_groups(program: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    targets = program.get("targets")
    if not isinstance(targets, dict):
        return {"in_scope": [], "out_of_scope": []}
    return {
        "in_scope": _target_list(targets.get("in_scope")),
        "out_of_scope": _target_list(targets.get("out_of_scope")),
    }


def _target_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _hackerone_target_types(targets: list[dict[str, Any]]) -> Counter[str]:
    return Counter(_slug(_string(target.get("asset_type")) or "unknown") for target in targets)


def _bugcrowd_target_types(targets: list[dict[str, Any]]) -> Counter[str]:
    return Counter(_slug(_string(target.get("type")) or "unknown") for target in targets)


def _hackerone_bounty_eligible_count(targets: list[dict[str, Any]]) -> int:
    return sum(1 for target in targets if target.get("eligible_for_bounty") is True)


def _signals_from_target_counts(count: int, target_types: Counter[str]) -> dict[str, Any]:
    if count == 0:
        clarity = "low"
        complexity = "unknown"
        scope = "unknown"
    elif count <= 3:
        clarity = "high"
        complexity = "medium"
        scope = "small"
    elif count <= 20:
        clarity = "medium"
        complexity = "medium"
        scope = "large"
    else:
        clarity = "medium"
        complexity = "high"
        scope = "large"

    tech = sorted(label for label in target_types if label and label != "unknown")
    return {
        "requires_secret_access": False,
        "requires_prompt_exfiltration": False,
        "requires_token_or_unknown_asset": False,
        "star_gated": False,
        "duplicate_pr_swarm": False,
        "clarity": clarity,
        "repo_activity": "unknown",
        "competition": "unknown",
        "complexity": complexity,
        "tech": tech,
        "scope": scope,
        "acceptance_criteria": [
            "Review only listed in-scope targets manually before acting",
            "Confirm current program rules on the public platform page before testing",
        ],
    }


def _dedupe_id(base_id: str, seen_ids: Counter[str], index: int) -> str:
    seen_ids[base_id] += 1
    if seen_ids[base_id] == 1:
        return base_id
    return f"{base_id}-{index + 1}"


def _labels(values: list[str | None]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        label = _slug(value)
        if label and label not in seen:
            labels.append(label)
            seen.add(label)
    return labels


def _submission_state_label(value: Any) -> str | None:
    state = _string(value)
    return f"submission-{_slug(state)}" if state else None


def _submission_state_sentence(value: Any) -> str:
    state = _string(value)
    return f"Submission state: {state or 'unknown'}."


def _url_tail(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    parts = [part for part in parsed.path.split("/") if part]
    return parts[-1] if parts else None


def _slug(value: str | None) -> str:
    if not value:
        return "unknown"
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unknown"


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _safe_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _safe_number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    return None
