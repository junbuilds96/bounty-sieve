from __future__ import annotations

import pytest

from bounty_sieve.opportunities import OpportunityValidationError, normalize_opportunities


def test_normalize_opportunities_rejects_duplicate_normalized_ids() -> None:
    with pytest.raises(OpportunityValidationError) as excinfo:
        normalize_opportunities(
            [
                {
                    "id": " duplicate-id ",
                    "title": "Fix docs",
                    "summary": "Clarify public setup docs.",
                },
                {
                    "id": "duplicate-id",
                    "title": "Fix tests",
                    "summary": "Stabilize a deterministic public test.",
                },
            ]
        )

    message = str(excinfo.value)
    assert 'duplicate id "duplicate-id"' in message
    assert "opportunities[0].id" in message
    assert "opportunities[1].id" in message
    assert "earlier index 0" in message
    assert "later index 1" in message


def test_normalize_opportunities_preserves_metadata_and_repo_health_signals() -> None:
    opportunities = normalize_opportunities(
        [
            {
                "id": "github-example-app-1",
                "title": "Fix docs quickstart",
                "summary": "Tiny docs task.",
                "signals": {
                    "repo_activity": "low",
                    "repo_activity_reason": "repository is archived",
                    "repo_health_stale": True,
                    "repo_archived": True,
                },
                "metadata": {
                    "github": {
                        "repo_health": {
                            "stars": 12,
                            "open_issues_count": 4,
                            "archived": True,
                            "pushed_at": "2024-01-01T00:00:00Z",
                            "updated_at": "2024-01-02T00:00:00Z",
                            "repo_activity": "low",
                            "reason": "repository is archived",
                        }
                    }
                },
            }
        ]
    )

    assert opportunities[0]["metadata"]["github"]["repo_health"] == {
        "stars": 12,
        "open_issues_count": 4,
        "archived": True,
        "pushed_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "repo_activity": "low",
        "reason": "repository is archived",
    }
    assert opportunities[0]["signals"]["repo_activity"] == "low"
    assert opportunities[0]["signals"]["repo_activity_reason"] == "repository is archived"
    assert opportunities[0]["signals"]["repo_health_stale"] is True
    assert opportunities[0]["signals"]["repo_archived"] is True
