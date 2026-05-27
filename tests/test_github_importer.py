from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from bounty_sieve.github_importer import (
    GitHubIssueRef,
    github_issue_to_opportunity,
    import_github_search,
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


def test_github_search_builds_search_url_filters_pull_requests_and_fetches_issue_comments(
    monkeypatch,
) -> None:
    calls = []
    search_payload = {
        "items": [
            {
                "title": "Fix public docs bounty ($50)",
                "body": "Acceptance criteria\n- Update README",
                "html_url": "https://github.com/example/widgets/issues/42",
                "repository_url": "https://api.github.com/repos/example/widgets",
                "labels": [{"name": "documentation"}],
                "state": "open",
                "number": 42,
                "comments": 1,
                "created_at": "2026-05-01T00:00:00Z",
                "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "assignees": [],
            },
            {
                "title": "Already a PR",
                "body": "Do not import pull requests.",
                "html_url": "https://github.com/example/widgets/pull/99",
                "repository_url": "https://api.github.com/repos/example/widgets",
                "labels": [],
                "state": "open",
                "number": 99,
                "comments": 3,
                "pull_request": {"url": "https://api.github.com/repos/example/widgets/pulls/99"},
            },
            {
                "title": "Fix a typo",
                "body": "Tiny docs issue.",
                "html_url": "https://github.com/example/widgets/issues/43",
                "repository_url": "https://api.github.com/repos/example/widgets",
                "labels": [{"name": "documentation"}],
                "state": "open",
                "number": 43,
                "comments": 0,
                "created_at": "2026-05-01T00:00:00Z",
                "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "assignees": [],
            },
        ]
    }
    comments_payload = [{"body": "Still open."}]

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        if len(calls) == 1:
            return FakeResponse(search_payload)
        if request.full_url == "https://api.github.com/repos/example/widgets/issues/42/comments":
            return FakeResponse(comments_payload)
        raise AssertionError(f"unexpected URL fetched: {request.full_url}")

    monkeypatch.setattr("bounty_sieve.github_importer.urlopen", fake_urlopen)

    opportunities = import_github_search('label:"good first issue" bounty', 25)

    search_url = urlparse(calls[0][0].full_url)
    assert search_url.scheme == "https"
    assert search_url.netloc == "api.github.com"
    assert search_url.path == "/search/issues"
    assert parse_qs(search_url.query) == {
        "q": ['label:"good first issue" bounty'],
        "per_page": ["25"],
    }
    assert [call[0].full_url for call in calls[1:]] == [
        "https://api.github.com/repos/example/widgets/issues/42/comments"
    ]
    assert [opportunity["id"] for opportunity in opportunities] == [
        "github-example-widgets-42",
        "github-example-widgets-43",
    ]
    assert opportunities[0]["metadata"]["github"]["comments_count"] == 1
    assert opportunities[1]["metadata"]["github"]["comments_count"] == 0
    assert opportunities[0]["signals"]["acceptance_criteria"] == ["Update README"]
    assert "pull/99" not in json.dumps(opportunities)


def test_github_search_repo_health_fetches_repo_metadata_once_per_repo(
    monkeypatch,
) -> None:
    calls = []
    search_payload = {
        "items": [
            {
                "title": "Fix docs bounty ($50)",
                "body": "Acceptance criteria\n- Update README",
                "html_url": "https://github.com/example/widgets/issues/42",
                "repository_url": "https://api.github.com/repos/example/widgets",
                "labels": [{"name": "documentation"}],
                "state": "open",
                "number": 42,
                "comments": 0,
                "created_at": "2026-05-01T00:00:00Z",
                "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "assignees": [],
            },
            {
                "title": "Fix another docs issue",
                "body": "Small public docs issue.",
                "html_url": "https://github.com/example/widgets/issues/43",
                "repository_url": "https://api.github.com/repos/example/widgets",
                "labels": [{"name": "documentation"}],
                "state": "open",
                "number": 43,
                "comments": 0,
                "created_at": "2026-05-01T00:00:00Z",
                "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "assignees": [],
            },
        ]
    }
    repo_payload = {
        "stargazers_count": 123,
        "open_issues_count": 7,
        "archived": True,
        "pushed_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
    }

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        if request.full_url.startswith("https://api.github.com/search/issues?"):
            return FakeResponse(search_payload)
        if request.full_url == "https://api.github.com/repos/example/widgets":
            return FakeResponse(repo_payload)
        raise AssertionError(f"unexpected URL fetched: {request.full_url}")

    monkeypatch.setenv("GITHUB_TOKEN", "secret-test-token")
    monkeypatch.setattr("bounty_sieve.github_importer.urlopen", fake_urlopen)

    opportunities = import_github_search("bounty docs", 10, include_repo_health=True)

    assert [call[0].full_url for call in calls[1:]] == [
        "https://api.github.com/repos/example/widgets"
    ]
    assert calls[1][0].headers["Authorization"] == "Bearer secret-test-token"
    health = opportunities[0]["metadata"]["github"]["repo_health"]
    assert health == {
        "stars": 123,
        "open_issues_count": 7,
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
    assert opportunities[1]["metadata"]["github"]["repo_health"] == health
    assert "secret-test-token" not in json.dumps(opportunities)


def test_github_search_canonicalizes_output_url_from_repository_ref(monkeypatch) -> None:
    search_payload = {
        "items": [
            {
                "title": "Fix public docs bounty",
                "body": "Small public docs issue.",
                "html_url": "https://attacker.example/collect",
                "repository_url": "https://api.github.com/repos/example/widgets",
                "labels": [{"name": "documentation"}],
                "state": "open",
                "number": 42,
                "comments": 0,
                "created_at": "2026-05-01T00:00:00Z",
                "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "assignees": [],
            },
        ]
    }

    def fake_urlopen(request, timeout):
        return FakeResponse(search_payload)

    monkeypatch.setattr("bounty_sieve.github_importer.urlopen", fake_urlopen)

    opportunities = import_github_search("bounty", 1)

    assert opportunities[0]["url"] == "https://github.com/example/widgets/issues/42"
    assert "attacker.example" not in json.dumps(opportunities)


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
