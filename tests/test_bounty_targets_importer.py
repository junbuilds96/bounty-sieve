from __future__ import annotations

import json

import pytest

from bounty_sieve.bounty_targets_importer import (
    BountyTargetsDataImportError,
    import_bounty_targets_data,
)


def test_import_hackerone_bounty_targets_data_normalizes_program_without_raw_instructions(
    tmp_path,
) -> None:
    source = tmp_path / "hackerone.json"
    source.write_text(
        json.dumps(
            [
                {
                    "id": 101,
                    "handle": "example-co",
                    "name": "Example Co",
                    "url": "https://hackerone.com/example-co",
                    "website": "https://example.test",
                    "offers_bounties": True,
                    "offers_swag": False,
                    "managed_program": True,
                    "allows_bounty_splitting": False,
                    "response_efficiency_percentage": 95,
                    "submission_state": "open",
                    "targets": {
                        "in_scope": [
                            {
                                "asset_identifier": "app.example.test",
                                "asset_type": "URL",
                                "eligible_for_bounty": True,
                                "eligible_for_submission": True,
                                "instruction": "Do not copy RAW_TARGET_INSTRUCTION_SENTINEL into output.",
                                "max_severity": "critical",
                            },
                            {
                                "asset_identifier": "api.example.test",
                                "asset_type": "API",
                                "eligible_for_bounty": False,
                                "eligible_for_submission": True,
                                "instruction": "A" * 2000,
                            },
                        ],
                        "out_of_scope": [
                            {
                                "asset_identifier": "internal.example.test",
                                "asset_type": "URL",
                            }
                        ],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    opportunities = import_bounty_targets_data(source, "hackerone")

    assert len(opportunities) == 1
    opportunity = opportunities[0]
    serialized = json.dumps(opportunity)
    assert opportunity["id"] == "hackerone-example-co"
    assert opportunity["title"] == "HackerOne program: Example Co"
    assert opportunity["platform"] == "hackerone"
    assert opportunity["source"] == "bounty-targets-data"
    assert opportunity["reward"] == {"amount": 0, "currency": "USD", "type": "conditional"}
    assert opportunity["signals"]["clarity"] == "high"
    assert opportunity["signals"]["scope"] == "small"
    assert opportunity["signals"]["tech"] == ["api", "url"]
    assert opportunity["metadata"]["bounty_targets_data"]["in_scope_count"] == 2
    assert opportunity["metadata"]["bounty_targets_data"]["out_of_scope_count"] == 1
    assert opportunity["metadata"]["bounty_targets_data"]["in_scope_bounty_eligible_count"] == 1
    assert "RAW_TARGET_INSTRUCTION_SENTINEL" not in serialized
    assert "A" * 100 not in serialized
    assert len(opportunity["summary"]) <= 320


def test_import_bugcrowd_bounty_targets_data_normalizes_program(tmp_path) -> None:
    source = tmp_path / "bugcrowd.json"
    source.write_text(
        json.dumps(
            [
                {
                    "name": "Example Bugcrowd",
                    "url": "https://bugcrowd.com/engagements/example-bugcrowd",
                    "allows_disclosure": True,
                    "managed_by_bugcrowd": True,
                    "safe_harbor": "full",
                    "max_payout": 7500,
                    "targets": {
                        "in_scope": [
                            {
                                "type": "website",
                                "target": "https://www.example.test",
                                "uri": "https://www.example.test",
                                "name": "Example website",
                            },
                            {
                                "type": "api",
                                "target": "https://api.example.test",
                                "uri": "https://api.example.test",
                                "name": "Example API",
                            },
                        ],
                        "out_of_scope": [{"type": "other", "target": "example staff"}],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    opportunities = import_bounty_targets_data(source, "bugcrowd")

    assert opportunities[0]["id"] == "bugcrowd-example-bugcrowd"
    assert opportunities[0]["title"] == "Bugcrowd program: Example Bugcrowd"
    assert opportunities[0]["reward"] == {
        "amount": 7500,
        "currency": "USD",
        "type": "estimated",
    }
    assert opportunities[0]["labels"] == [
        "bounty-targets-data",
        "bugcrowd",
        "managed",
        "allows-disclosure",
        "safe-harbor-full",
        "website",
        "api",
    ]
    assert opportunities[0]["signals"]["tech"] == ["api", "website"]
    assert opportunities[0]["metadata"]["bounty_targets_data"]["target_types"] == {
        "website": 1,
        "api": 1,
    }


def test_import_bounty_targets_data_rejects_non_local_input() -> None:
    with pytest.raises(BountyTargetsDataImportError) as excinfo:
        import_bounty_targets_data("https://example.test/hackerone_data.json", "hackerone")

    assert "--input must be a local JSON file path" in str(excinfo.value)
