"""Opportunity import validation and normalization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bounty_sieve.io import read_json


BOOLEAN_SIGNAL_FIELDS = {
    "requires_secret_access",
    "requires_prompt_exfiltration",
    "requires_token_or_unknown_asset",
    "star_gated",
    "duplicate_pr_swarm",
    "has_reproduction_steps",
    "has_acceptance_criteria",
    "maintainer_engaged",
    "assigned",
}

ENUM_SIGNAL_FIELDS = {
    "clarity": {"high", "medium", "low", "unknown"},
    "repo_activity": {"active", "low", "unknown"},
    "competition": {"low", "medium", "high", "unknown"},
    "complexity": {"low", "medium", "high", "unknown"},
    "scope": {"tiny", "small", "large", "unsafe", "unknown"},
    "issue_state": {"open", "closed", "unknown"},
}

REWARD_TYPES = {"fixed", "estimated", "conditional", "claimed", "unknown"}

DEFAULT_SIGNALS: dict[str, Any] = {
    "requires_secret_access": False,
    "requires_prompt_exfiltration": False,
    "requires_token_or_unknown_asset": False,
    "star_gated": False,
    "duplicate_pr_swarm": False,
    "has_reproduction_steps": False,
    "has_acceptance_criteria": False,
    "maintainer_engaged": False,
    "assigned": False,
    "clarity": "unknown",
    "repo_activity": "unknown",
    "competition": "unknown",
    "complexity": "unknown",
    "tech": [],
    "scope": "unknown",
    "issue_state": "unknown",
    "acceptance_criteria": [],
}


class OpportunityValidationError(ValueError):
    """Raised when a user-provided opportunity file is not usable."""


def load_json_opportunities(path: str | Path) -> list[dict[str, Any]]:
    """Load and validate user-provided opportunities from JSON."""
    try:
        payload = read_json(path)
    except FileNotFoundError as exc:
        raise OpportunityValidationError(f"input file not found: {path}") from exc
    except OSError as exc:
        raise OpportunityValidationError(f"could not read input file {path}: {exc}") from exc
    except ValueError as exc:
        raise OpportunityValidationError(f"input file is not valid JSON: {exc}") from exc

    opportunities = _extract_opportunity_list(payload)
    return normalize_opportunities(opportunities)


def normalize_opportunities(opportunities: list[Any]) -> list[dict[str, Any]]:
    """Validate and normalize opportunity objects already loaded in memory."""
    if not isinstance(opportunities, list):
        raise OpportunityValidationError("opportunities must be a list")

    normalized: list[dict[str, Any]] = []
    seen_ids: dict[str, int] = {}
    for index, item in enumerate(opportunities):
        path = f"opportunities[{index}]"
        normalized_item = _normalize_opportunity(item, path)
        opportunity_id = normalized_item["id"]
        if opportunity_id in seen_ids:
            earlier_index = seen_ids[opportunity_id]
            raise OpportunityValidationError(
                f'{path}.id duplicate id "{opportunity_id}"; '
                f"first seen at opportunities[{earlier_index}].id "
                f"(earlier index {earlier_index}, later index {index})"
            )
        seen_ids[opportunity_id] = index
        normalized.append(normalized_item)
    return normalized


def _extract_opportunity_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and "opportunities" in payload:
        opportunities = payload["opportunities"]
        if isinstance(opportunities, list):
            return opportunities
        raise OpportunityValidationError("opportunities must be a list")
    raise OpportunityValidationError(
        'top-level JSON must be a list or an object with an "opportunities" list'
    )


def _normalize_opportunity(item: Any, path: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise OpportunityValidationError(f"{path} must be an object")

    normalized = dict(item)
    for field in ("id", "title", "summary"):
        normalized[field] = _required_string(item, field, path)

    for field in ("url", "platform", "repo", "source"):
        if field in item:
            normalized[field] = _optional_string(item[field], f"{path}.{field}")
        else:
            normalized[field] = "json" if field == "source" else None

    if "labels" in item:
        normalized["labels"] = _string_list(item["labels"], f"{path}.labels")
    else:
        normalized["labels"] = []

    normalized["reward"] = _normalize_reward(item.get("reward", {}), f"{path}.reward")
    normalized["signals"] = _normalize_signals(item.get("signals", {}), f"{path}.signals")
    return normalized


def _required_string(item: dict[str, Any], field: str, path: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise OpportunityValidationError(f"{path}.{field} is required and must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise OpportunityValidationError(f"{path} must be a string or null")
    return value.strip() or None


def _string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        raise OpportunityValidationError(f"{path} must be a list of strings")
    strings: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise OpportunityValidationError(f"{path}[{index}] must be a non-empty string")
        strings.append(item.strip())
    return strings


def _normalize_reward(value: Any, path: str) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise OpportunityValidationError(f"{path} must be an object")

    amount = value.get("amount", 0)
    if not isinstance(amount, int | float) or isinstance(amount, bool):
        raise OpportunityValidationError(f"{path}.amount must be a number")
    if amount < 0:
        raise OpportunityValidationError(f"{path}.amount must be zero or greater")

    currency = value.get("currency", "USD")
    if not isinstance(currency, str) or not currency.strip():
        raise OpportunityValidationError(f"{path}.currency must be a non-empty string")

    reward_type = value.get("type", "unknown")
    if not isinstance(reward_type, str) or reward_type not in REWARD_TYPES:
        allowed = ", ".join(sorted(REWARD_TYPES))
        raise OpportunityValidationError(f"{path}.type must be one of: {allowed}")

    return {
        **value,
        "amount": amount,
        "currency": currency.strip().upper(),
        "type": reward_type,
    }


def _normalize_signals(value: Any, path: str) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise OpportunityValidationError(f"{path} must be an object")

    normalized = {**DEFAULT_SIGNALS, **value}

    for field in BOOLEAN_SIGNAL_FIELDS:
        if not isinstance(normalized[field], bool):
            raise OpportunityValidationError(f"{path}.{field} must be true or false")

    for field, allowed_values in ENUM_SIGNAL_FIELDS.items():
        signal = normalized[field]
        if not isinstance(signal, str) or signal not in allowed_values:
            allowed = ", ".join(sorted(allowed_values))
            raise OpportunityValidationError(f"{path}.{field} must be one of: {allowed}")

    normalized["tech"] = _string_list(normalized["tech"], f"{path}.tech")
    normalized["acceptance_criteria"] = _string_list(
        normalized["acceptance_criteria"], f"{path}.acceptance_criteria"
    )
    return normalized
