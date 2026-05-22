from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bounty_sieve.github_importer import (
    GitHubIssueRef,
    github_issue_to_opportunity,
    import_github_issue_url,
    import_url_list,
)


class FakeResponse:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_github_issue_fetch_uses_mocked_network_and_normalizes(monkeypatch) -> None:
    calls = []
    issue_payload = {
        "title": "Add README verification command ($100 bounty)",
        "body": (
            "The README install flow needs a public verification command.\n\n"
            "Acceptance criteria\n"
            "- README shows one command users can run\n"
            "- Example output is included\n"
        ),
        "html_url": "https://github.com/example/widgets/issues/42",
        "labels": [{"name": "documentation"}, {"name": "good first issue"}],
        "state": "open",
        "comments": 2,
        "comments_url": "https://api.github.com/repos/example/widgets/issues/42/comments",
        "created_at": "2026-05-01T00:00:00Z",
        "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "assignees": [],
    }
    comments_payload = [{"body": "Looks unclaimed."}, {"body": "Scope is docs only."}]

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        if len(calls) == 1:
            return FakeResponse(issue_payload)
        return FakeResponse(comments_payload)

    monkeypatch.setenv("GITHUB_TOKEN", "secret-test-token")
    monkeypatch.setattr("bounty_sieve.github_importer.urlopen", fake_urlopen)

    opportunity = import_github_issue_url("https://github.com/example/widgets/issues/42")

    assert len(calls) == 2
    assert [call[0].full_url for call in calls] == [
        "https://api.github.com/repos/example/widgets/issues/42",
        "https://api.github.com/repos/example/widgets/issues/42/comments",
    ]
    assert calls[0][0].headers["Authorization"] == "Bearer secret-test-token"
    assert "secret-test-token" not in json.dumps(opportunity)
    assert opportunity["id"] == "github-example-widgets-42"
    assert opportunity["repo"] == "example/widgets"
    assert opportunity["reward"] == {"amount": 100, "currency": "USD", "type": "fixed"}
    assert opportunity["signals"]["clarity"] == "high"
    assert opportunity["signals"]["scope"] == "small"
    assert opportunity["signals"]["requires_secret_access"] is False
    assert opportunity["signals"]["acceptance_criteria"] == [
        "README shows one command users can run",
        "Example output is included",
    ]


def test_github_issue_fetch_ignores_malicious_payload_comments_url(monkeypatch) -> None:
    calls = []
    issue_payload = {
        "title": "Fix a docs typo",
        "body": "Small public docs issue.",
        "html_url": "https://github.com/example/widgets/issues/42",
        "labels": [{"name": "documentation"}],
        "state": "open",
        "comments": 1,
        "comments_url": "https://attacker.example/collect?repo=example/widgets",
        "created_at": "2026-05-01T00:00:00Z",
        "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "assignees": [],
    }
    comments_payload = [{"body": "Still open."}]

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        if request.full_url == "https://api.github.com/repos/example/widgets/issues/42":
            return FakeResponse(issue_payload)
        if request.full_url == "https://api.github.com/repos/example/widgets/issues/42/comments":
            return FakeResponse(comments_payload)
        raise AssertionError(f"unexpected URL fetched: {request.full_url}")

    monkeypatch.setattr("bounty_sieve.github_importer.urlopen", fake_urlopen)

    opportunity = import_github_issue_url("https://github.com/example/widgets/issues/42")

    assert [call[0].full_url for call in calls] == [
        "https://api.github.com/repos/example/widgets/issues/42",
        "https://api.github.com/repos/example/widgets/issues/42/comments",
    ]
    assert opportunity["signals"]["competition"] == "low"
    assert "attacker.example" not in json.dumps(opportunity)


def test_github_issue_parser_flags_unsafe_and_competitive_signals() -> None:
    opportunity = github_issue_to_opportunity(
        "https://github.com/example/wallet/issues/7",
        GitHubIssueRef(owner="example", repo="wallet", number=7),
        {
            "title": "Recover unknown token payout",
            "body": "Connect wallet and share proof before eligibility. Star the repo first.",
            "html_url": "https://github.com/example/wallet/issues/7",
            "labels": [{"name": "bounty"}],
            "state": "open",
            "comments": 9,
            "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "assignees": [],
        },
        [{"body": "Already claimed by multiple PRs."}],
    )

    assert opportunity["signals"]["requires_token_or_unknown_asset"] is True
    assert opportunity["signals"]["star_gated"] is True
    assert opportunity["signals"]["duplicate_pr_swarm"] is True
    assert opportunity["signals"]["competition"] == "high"
    assert opportunity["signals"]["scope"] == "unsafe"


def test_url_list_importer_skips_unsupported_urls_without_crashing(
    tmp_path: Path, monkeypatch
) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text(
        "\n".join(
            [
                "# comment",
                "https://github.com/example/widgets/issues/42",
                "https://example.com/bounty/1",
                "https://github.com/example/widgets/pull/9",
            ]
        ),
        encoding="utf-8",
    )

    def fake_import(url: str) -> dict[str, Any]:
        return {"id": "imported", "title": "Imported", "summary": url}

    monkeypatch.setattr("bounty_sieve.github_importer.import_github_issue_url", fake_import)

    opportunities, warnings = import_url_list(str(urls))

    assert opportunities == [
        {
            "id": "imported",
            "title": "Imported",
            "summary": "https://github.com/example/widgets/issues/42",
        }
    ]
    assert len(warnings) == 2
    assert "skipped unsupported URL" in warnings[0]
