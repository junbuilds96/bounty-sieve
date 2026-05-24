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
