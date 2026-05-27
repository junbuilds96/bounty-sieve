from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from email.message import Message
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import bounty_sieve
from bounty_sieve.__main__ import main as cli_main
from bounty_sieve.doctor import run_doctor
from bounty_sieve.github_importer import GitHubImportError
from bounty_sieve.opportunities import OpportunityValidationError


REPO_ROOT = Path(__file__).resolve().parents[1]


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(REPO_ROOT)
        if not existing_pythonpath
        else f"{REPO_ROOT}{os.pathsep}{existing_pythonpath}"
    )
    return env


def run_cli(
    *args: str, cwd: Path | None = None, input: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "bounty_sieve", *args],
        check=True,
        text=True,
        capture_output=True,
        input=input,
        cwd=cwd,
        env=_subprocess_env() if cwd else None,
    )


def run_cli_unchecked(
    *args: str, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "bounty_sieve", *args],
        check=False,
        text=True,
        capture_output=True,
        cwd=cwd,
        env=_subprocess_env() if cwd else None,
    )


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def assert_actionability_shape(actionability: dict) -> None:
    assert set(actionability) == {
        "label",
        "timeliness_score",
        "confidence_score",
        "reasons",
    }
    assert isinstance(actionability["label"], str)
    assert isinstance(actionability["timeliness_score"], int)
    assert isinstance(actionability["confidence_score"], int)
    assert isinstance(actionability["reasons"], list)
    assert all(isinstance(reason, str) for reason in actionability["reasons"])


def stdin_opportunities_json(*ids: str) -> str:
    return json.dumps(
        {
            "opportunities": [
                {
                    "id": item_id,
                    "title": f"Fix {item_id}",
                    "summary": f"Small public task for {item_id}.",
                }
                for item_id in ids
            ]
        }
    )


def shortlist_opportunities_json() -> str:
    return json.dumps(
        {
            "opportunities": [
                {
                    "id": "watch-complex",
                    "title": "High reward but complex backend refactor",
                    "summary": "Large task with a fixed reward.",
                    "url": "https://github.com/example/app/issues/3",
                    "reward": {"amount": 1000, "currency": "USD", "type": "fixed"},
                    "signals": {
                        "clarity": "high",
                        "repo_activity": "active",
                        "competition": "low",
                        "complexity": "high",
                        "scope": "large",
                        "tech": ["python"],
                    },
                },
                {
                    "id": "pursue-lower-roi",
                    "title": "Fix flaky CLI test",
                    "summary": "Small deterministic test repair.",
                    "url": "https://github.com/example/app/issues/2",
                    "reward": {"amount": 150, "currency": "USD", "type": "fixed"},
                    "signals": {
                        "clarity": "medium",
                        "repo_activity": "active",
                        "competition": "low",
                        "complexity": "low",
                        "scope": "small",
                        "tech": ["python"],
                    },
                },
                {
                    "id": "pursue-higher-roi",
                    "title": "Fix docs quickstart",
                    "summary": "Tiny docs task with clear acceptance criteria.",
                    "url": "https://github.com/example/app/issues/1",
                    "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                    "signals": {
                        "clarity": "high",
                        "repo_activity": "active",
                        "competition": "low",
                        "complexity": "low",
                        "scope": "tiny",
                        "tech": ["markdown", "cli"],
                    },
                },
                {
                    "id": "reject-wallet",
                    "title": "Connect wallet for unknown token bounty",
                    "summary": "Unsafe wallet requirement.",
                    "url": "https://github.com/example/app/issues/4",
                    "reward": {"amount": 500, "currency": "USD", "type": "fixed"},
                    "signals": {
                        "requires_token_or_unknown_asset": True,
                        "clarity": "high",
                        "repo_activity": "active",
                        "competition": "low",
                        "complexity": "low",
                        "scope": "small",
                        "tech": ["python"],
                    },
                },
            ]
        }
    )


def compare_before_after_json() -> tuple[str, str]:
    before = {
        "opportunities": [
            {
                "id": "removed-task",
                "title": "Removed task title",
                "summary": "Removed task summary.",
                "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                "signals": {
                    "clarity": "high",
                    "repo_activity": "active",
                    "competition": "low",
                    "complexity": "low",
                    "scope": "tiny",
                    "tech": ["python"],
                },
            },
            {
                "id": "rec-change",
                "title": "Recommendation change title",
                "summary": "Recommendation change summary.",
                "signals": {"clarity": "low"},
            },
            {
                "id": "roi-change",
                "title": "ROI change title",
                "summary": "ROI change summary.",
                "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                "signals": {
                    "clarity": "high",
                    "repo_activity": "active",
                    "competition": "low",
                    "complexity": "low",
                    "scope": "tiny",
                    "tech": ["python"],
                },
            },
            {
                "id": "unchanged-task",
                "title": "Unchanged title",
                "summary": "Unchanged summary.",
                "reward": {"amount": 50, "currency": "USD", "type": "fixed"},
                "signals": {
                    "clarity": "medium",
                    "repo_activity": "active",
                    "competition": "low",
                    "complexity": "low",
                    "scope": "small",
                    "tech": ["python"],
                },
            },
        ]
    }
    after = {
        "opportunities": [
            {
                "id": "added-task",
                "title": "Added task title",
                "summary": "Added task summary.",
                "signals": {"clarity": "low"},
            },
            {
                "id": "rec-change",
                "title": "Recommendation change title",
                "summary": "Recommendation change summary.",
                "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                "signals": {
                    "clarity": "high",
                    "repo_activity": "active",
                    "competition": "low",
                    "complexity": "low",
                    "scope": "tiny",
                    "tech": ["python"],
                },
            },
            {
                "id": "roi-change",
                "title": "ROI change title",
                "summary": "ROI change summary.",
                "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                "signals": {
                    "clarity": "high",
                    "repo_activity": "active",
                    "competition": "low",
                    "complexity": "low",
                    "scope": "tiny",
                    "tech": ["python", "pytest", "markdown"],
                },
            },
            {
                "id": "unchanged-task",
                "title": "Unchanged title",
                "summary": "Unchanged summary.",
                "reward": {"amount": 50, "currency": "USD", "type": "fixed"},
                "signals": {
                    "clarity": "medium",
                    "repo_activity": "active",
                    "competition": "low",
                    "complexity": "low",
                    "scope": "small",
                    "tech": ["python"],
                },
            },
        ]
    }
    return json.dumps(before), json.dumps(after)


def test_package_metadata_uses_bounty_sieve_names() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "bounty-sieve"
    assert pyproject["project"]["version"] == "0.3.0"
    assert bounty_sieve.__version__ == "0.3.0"
    assert (
        pyproject["project"]["description"]
        == "Offline-by-default read-only bounty opportunity intake, triage, and safety filtering."
    )
    assert pyproject["project"]["license"] == "MIT"
    assert pyproject["project"]["scripts"] == {
        "bounty-sieve": "bounty_sieve.__main__:main"
    }
    assert pyproject["tool"]["setuptools"]["packages"]["find"]["include"] == [
        "bounty_sieve*"
    ]


def test_cli_help_lists_offline_demo_commands() -> None:
    result = run_cli_unchecked("--help")

    assert result.returncode == 0
    assert "Offline-by-default read-only bounty opportunity intake" in result.stdout
    assert "validate" in result.stdout
    assert "discover" in result.stdout
    assert "score" in result.stdout
    assert "compare" in result.stdout
    assert "rank" in result.stdout
    assert "search-preview" in result.stdout
    assert "shortlist" in result.stdout
    assert "next" in result.stdout
    assert "explain" in result.stdout
    assert "report" in result.stdout
    assert "demo" in result.stdout
    assert "doctor" in result.stdout


def test_cli_version_prints_package_version() -> None:
    result = run_cli_unchecked("--version")

    assert result.returncode == 0
    assert result.stdout == f"bounty-sieve {bounty_sieve.__version__}\n"
    assert result.stderr == ""


def test_doctor_reports_success_in_human_output() -> None:
    result = run_cli("doctor")

    assert result.stderr == ""
    assert "OK python_version:" in result.stdout
    assert "OK package_import:" in result.stdout
    assert "OK minimal_example:" in result.stdout
    assert "OK fixture_pipeline:" in result.stdout
    assert result.stdout.endswith("Doctor passed\n")


def test_doctor_json_reports_success_without_extra_prose() -> None:
    result = run_cli("doctor", "--json")

    payload = json.loads(result.stdout)
    assert result.stderr == ""
    assert payload["ok"] is True
    assert {check["name"] for check in payload["checks"]} == {
        "python_version",
        "package_import",
        "minimal_example",
        "fixture_pipeline",
    }
    assert all(check["status"] == "pass" for check in payload["checks"])


def test_doctor_accepts_user_example_file_through_cli(tmp_path: Path) -> None:
    example = tmp_path / "user-opportunities.json"
    example.write_text(stdin_opportunities_json("user-example"), encoding="utf-8")

    result = run_cli("doctor", "--example", str(example))

    assert result.stderr == ""
    assert "OK minimal_example:" in result.stdout
    assert f"1 opportunity validated from {example}" in result.stdout
    assert "Doctor passed\n" in result.stdout


def test_doctor_json_reports_missing_user_example_through_cli(tmp_path: Path) -> None:
    example = tmp_path / "missing-opportunities.json"

    result = run_cli_unchecked("doctor", "--example", str(example), "--json")

    payload = json.loads(result.stdout)
    checks = {check["name"]: check for check in payload["checks"]}
    assert result.returncode == 1
    assert result.stderr == ""
    assert payload["ok"] is False
    assert checks["minimal_example"]["status"] == "fail"
    assert checks["minimal_example"]["details"]["message"] == f"example file missing: {example}"
    assert checks["fixture_pipeline"]["status"] == "pass"


def test_doctor_reports_representative_failure_for_missing_example(tmp_path: Path) -> None:
    result = run_doctor(example_path=tmp_path / "missing.json")

    checks = {check["name"]: check for check in result["checks"]}
    assert result["ok"] is False
    assert checks["minimal_example"]["status"] == "fail"
    assert "example file missing" in checks["minimal_example"]["details"]["message"]
    assert checks["fixture_pipeline"]["status"] == "pass"


def test_discover_help_lists_agent_intake_sources() -> None:
    result = run_cli_unchecked("discover", "--help")

    assert result.returncode == 0
    assert "bounty-targets-data" in result.stdout
    assert "--platform" in result.stdout
    assert "github-issue" in result.stdout
    assert "github-search" in result.stdout
    assert "url-list" in result.stdout
    assert "read-only public" in result.stdout
    assert "fetches" in result.stdout
    assert "Preview bounty-targets-data, github-issue, github-search, or url-list" in result.stdout
    assert "imports as compact JSON" in result.stdout


def test_cli_rejects_invalid_fixture_source(tmp_path: Path) -> None:
    out = tmp_path / "opportunities.json"

    result = run_cli_unchecked("discover", "--source", "network", "--out", str(out))

    assert result.returncode == 2
    assert "invalid choice" in result.stderr
    assert not out.exists()


def test_cli_github_issue_dry_run_prints_normalized_json_without_writing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    out = tmp_path / "should-not-exist.json"
    url = "https://github.com/example/widgets/issues/42"

    def fake_import(import_url: str) -> dict:
        return {
            "id": "github-example-widgets-42",
            "title": "Fix README install step",
            "summary": "Document the missing CLI install command.",
            "url": import_url,
            "platform": "github",
            "repo": "example/widgets",
            "source": "github-issue",
            "labels": ["documentation"],
            "reward": {"amount": 125, "currency": "usd", "type": "fixed"},
        }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("bounty_sieve.__main__.import_github_issue_url", fake_import)

    result = cli_main(
        [
            "discover",
            "--source",
            "github-issue",
            "--url",
            url,
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert result == 0
    assert captured.err == ""
    assert payload == [
        {
            "id": "github-example-widgets-42",
            "title": "Fix README install step",
            "summary": "Document the missing CLI install command.",
            "url": url,
            "platform": "github",
            "repo": "example/widgets",
            "source": "github-issue",
            "labels": ["documentation"],
            "reward": {"amount": 125, "currency": "USD", "type": "fixed"},
            "signals": {
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
            },
        }
    ]
    assert captured.out == json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []


def test_cli_github_search_dry_run_prints_normalized_json_without_writing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    out = tmp_path / "should-not-exist.json"

    def fake_import(query: str, limit: int) -> list[dict]:
        assert query == 'label:"good first issue" bounty'
        assert limit == 10
        return [
            {
                "id": "github-example-widgets-42",
                "title": "Fix README install step",
                "summary": "Document the missing CLI install command.",
                "url": "https://github.com/example/widgets/issues/42",
                "platform": "github",
                "repo": "example/widgets",
                "source": "github-issue",
                "labels": ["documentation"],
                "reward": {"amount": 125, "currency": "usd", "type": "fixed"},
            }
        ]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("bounty_sieve.__main__.import_github_search", fake_import)

    result = cli_main(
        [
            "discover",
            "--source",
            "github-search",
            "--query",
            'label:"good first issue" bounty',
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert result == 0
    assert captured.err == ""
    assert payload == [
        {
            "id": "github-example-widgets-42",
            "title": "Fix README install step",
            "summary": "Document the missing CLI install command.",
            "url": "https://github.com/example/widgets/issues/42",
            "platform": "github",
            "repo": "example/widgets",
            "source": "github-issue",
            "labels": ["documentation"],
            "reward": {"amount": 125, "currency": "USD", "type": "fixed"},
            "signals": {
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
            },
        }
    ]
    assert captured.out == json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []


def test_cli_url_list_dry_run_prints_normalized_json_without_out_and_keeps_warnings_on_stderr(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    urls = tmp_path / "urls.txt"
    out = tmp_path / "discovered.json"
    urls.write_text(
        "\n".join(
            [
                "https://github.com/example/widgets/issues/42",
                "https://example.com/bounty/1",
            ]
        ),
        encoding="utf-8",
    )

    def fake_import_url_list(path: str) -> tuple[list[dict], list[str]]:
        return (
            [
                {
                    "id": "github-example-widgets-42",
                    "title": "Fix README install step",
                    "summary": "Document the missing CLI install command.",
                    "url": "https://github.com/example/widgets/issues/42",
                    "platform": "github",
                    "repo": "example/widgets",
                    "source": "github-issue",
                    "labels": ["documentation"],
                    "reward": {"amount": 125, "currency": "usd", "type": "fixed"},
                }
            ],
            [f"{path}:2: skipped unsupported URL: https://example.com/bounty/1"],
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("bounty_sieve.__main__.import_url_list", fake_import_url_list)

    result = cli_main(
        [
            "discover",
            "--source",
            "url-list",
            "--input",
            str(urls),
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert result == 0
    assert captured.err == (
        f"warning: {urls}:2: skipped unsupported URL: https://example.com/bounty/1\n"
    )
    assert payload == [
        {
            "id": "github-example-widgets-42",
            "title": "Fix README install step",
            "summary": "Document the missing CLI install command.",
            "url": "https://github.com/example/widgets/issues/42",
            "platform": "github",
            "repo": "example/widgets",
            "source": "github-issue",
            "labels": ["documentation"],
            "reward": {"amount": 125, "currency": "USD", "type": "fixed"},
            "signals": {
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
            },
        }
    ]
    assert captured.out == json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
    assert not out.exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["urls.txt"]


def test_cli_dry_run_is_only_valid_for_github_issue_or_url_list(tmp_path: Path) -> None:
    for source in ("fixture", "json"):
        out = tmp_path / f"{source}.json"

        result = run_cli_unchecked("discover", "--source", source, "--out", str(out), "--dry-run")

        assert result.returncode == 2
        assert (
            "--dry-run can only be used with --source bounty-targets-data, --source github-issue, --source github-search, or --source url-list"
            in result.stderr
        )
        assert result.stdout == ""
        assert not out.exists()


def test_cli_github_search_argument_errors_do_not_fetch_network(tmp_path: Path) -> None:
    out = tmp_path / "discovered.json"
    cases = [
        (
            ["discover", "--source", "github-search", "--dry-run"],
            "--source github-search requires --query QUERY",
        ),
        (
            [
                "discover",
                "--source",
                "github-search",
                "--query",
                "bounty",
                "--url",
                "https://github.com/example/widgets/issues/42",
                "--dry-run",
            ],
            "--url cannot be used with --source github-search",
        ),
        (
            [
                "discover",
                "--source",
                "github-search",
                "--query",
                "bounty",
                "--input",
                str(tmp_path / "urls.txt"),
                "--dry-run",
            ],
            "--input cannot be used with --source github-search",
        ),
        (
            [
                "discover",
                "--source",
                "github-search",
                "--query",
                "bounty",
                "--limit",
                "51",
                "--dry-run",
            ],
            "--limit must be between 1 and 50",
        ),
    ]

    for args, message in cases:
        result = run_cli_unchecked(*args)

        assert result.returncode == 2
        assert message in result.stderr
        assert result.stdout == ""
        assert not out.exists()


def test_cli_discover_github_search_repo_health_dry_run_passes_flag(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    calls = []

    def fake_import(
        query: str,
        limit: int,
        include_repo_health: bool = False,
    ) -> list[dict]:
        calls.append((query, limit, include_repo_health))
        return [
            {
                "id": "github-example-app-1",
                "title": "Fix docs quickstart",
                "summary": "Tiny docs task.",
                "url": "https://github.com/example/app/issues/1",
                "platform": "github",
                "repo": "example/app",
                "source": "github-issue",
                "signals": {
                    "clarity": "high",
                    "repo_activity": "active",
                    "repo_activity_reason": "repository pushed within 180 days",
                    "repo_health_stale": False,
                    "repo_archived": False,
                    "competition": "low",
                    "complexity": "low",
                    "scope": "tiny",
                    "tech": ["markdown"],
                },
                "metadata": {
                    "github": {
                        "repo_health": {
                            "stars": 12,
                            "open_issues_count": 4,
                            "archived": False,
                            "pushed_at": "2026-05-20T00:00:00Z",
                            "updated_at": "2026-05-21T00:00:00Z",
                            "repo_activity": "active",
                            "reason": "repository pushed within 180 days",
                        }
                    }
                },
            }
        ]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("bounty_sieve.__main__.import_github_search", fake_import)

    result = cli_main(
        [
            "discover",
            "--source",
            "github-search",
            "--query",
            "bounty docs",
            "--repo-health",
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert result == 0
    assert calls == [("bounty docs", 10, True)]
    assert payload[0]["metadata"]["github"]["repo_health"]["stars"] == 12
    assert payload[0]["signals"]["repo_activity"] == "active"
    assert payload[0]["signals"]["repo_activity_reason"] == "repository pushed within 180 days"
    assert payload[0]["signals"]["repo_health_stale"] is False
    assert payload[0]["signals"]["repo_archived"] is False
    assert list(tmp_path.iterdir()) == []


def test_cli_discover_still_requires_out_without_dry_run(tmp_path: Path) -> None:
    result = run_cli_unchecked("discover", "--source", "fixture", cwd=tmp_path)

    assert result.returncode == 2
    assert "the following arguments are required: --out" in result.stderr
    assert result.stdout == ""
    assert list(tmp_path.iterdir()) == []


def test_cli_imports_user_json_opportunities(tmp_path: Path) -> None:
    source = tmp_path / "opportunities.json"
    out = tmp_path / "discovered.json"
    source.write_text(
        json.dumps(
            {
                "opportunities": [
                    {
                        "id": "user-docs-fix",
                        "title": "Clarify public setup docs",
                        "summary": "Add a verification command to public setup docs.",
                        "reward": {"amount": 90, "currency": "usd", "type": "fixed"},
                        "signals": {
                            "clarity": "high",
                            "repo_activity": "active",
                            "competition": "low",
                            "complexity": "low",
                            "scope": "tiny",
                            "tech": ["markdown", "cli"],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_cli("discover", "--source", "json", "--input", str(source), "--out", str(out))

    opportunities = read_json(out)
    assert result.stdout == ""
    assert result.stderr == ""
    assert opportunities[0]["id"] == "user-docs-fix"
    assert opportunities[0]["source"] == "json"
    assert opportunities[0]["reward"]["currency"] == "USD"
    assert opportunities[0]["signals"]["requires_secret_access"] is False
    assert opportunities[0]["signals"]["acceptance_criteria"] == []


def test_cli_imports_bounty_targets_data_with_summary_json(tmp_path: Path) -> None:
    source = tmp_path / "bugcrowd.synthetic.json"
    out = tmp_path / "discovered.json"
    source.write_text(
        json.dumps(
            [
                {
                    "name": "Example Bugcrowd",
                    "url": "https://bugcrowd.com/engagements/example-bugcrowd",
                    "allows_disclosure": True,
                    "managed_by_bugcrowd": True,
                    "safe_harbor": "full",
                    "max_payout": 5000,
                    "targets": {
                        "in_scope": [{"type": "website", "target": "https://www.example.test"}],
                        "out_of_scope": [],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    result = run_cli(
        "discover",
        "--source",
        "bounty-targets-data",
        "--platform",
        "bugcrowd",
        "--input",
        str(source),
        "--out",
        str(out),
        "--summary-json",
    )

    opportunities = read_json(out)
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "ok": True,
        "output": str(out),
        "total": 1,
        "ids": ["bugcrowd-example-bugcrowd"],
    }
    assert opportunities[0]["id"] == "bugcrowd-example-bugcrowd"
    assert opportunities[0]["source"] == "bounty-targets-data"
    assert opportunities[0]["platform"] == "bugcrowd"
    assert opportunities[0]["reward"] == {
        "amount": 5000,
        "currency": "USD",
        "type": "estimated",
    }


def test_cli_bounty_targets_data_dry_run_prints_normalized_json_without_writing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "hackerone.synthetic.json"
    out = tmp_path / "should-not-exist.json"
    source.write_text(
        json.dumps(
            [
                {
                    "handle": "example-co",
                    "name": "Example Co",
                    "url": "https://hackerone.com/example-co",
                    "offers_bounties": True,
                    "submission_state": "open",
                    "targets": {
                        "in_scope": [
                            {
                                "asset_identifier": "app.example.test",
                                "asset_type": "URL",
                                "instruction": "Do not copy SECRET=synthetic.",
                            }
                        ],
                        "out_of_scope": [],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    result = run_cli(
        "discover",
        "--source",
        "bounty-targets-data",
        "--platform",
        "hackerone",
        "--input",
        str(source),
        "--dry-run",
    )

    payload = json.loads(result.stdout)
    assert result.stderr == ""
    assert payload[0]["id"] == "hackerone-example-co"
    assert payload[0]["source"] == "bounty-targets-data"
    assert "SECRET" not in result.stdout
    assert "synthetic" not in result.stdout
    assert not out.exists()


def test_cli_bounty_targets_data_requires_platform_and_rejects_url_input(
    tmp_path: Path,
) -> None:
    out = tmp_path / "discovered.json"

    missing_platform = run_cli_unchecked(
        "discover",
        "--source",
        "bounty-targets-data",
        "--input",
        str(tmp_path / "synthetic.json"),
        "--out",
        str(out),
    )
    url_input = run_cli_unchecked(
        "discover",
        "--source",
        "bounty-targets-data",
        "--platform",
        "hackerone",
        "--input",
        "https://example.test/hackerone_data.json",
        "--out",
        str(out),
    )

    assert missing_platform.returncode == 2
    assert "--source bounty-targets-data requires --platform hackerone|bugcrowd" in (
        missing_platform.stderr
    )
    assert url_input.returncode == 2
    assert "--input must be a local JSON file path" in url_input.stderr
    assert not out.exists()


def test_cli_discover_summary_json_prints_machine_readable_stdout_after_writing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "opportunities.json"
    out = tmp_path / "discovered.json"
    source.write_text(
        json.dumps(
            {
                "opportunities": [
                    {
                        "id": "user-docs-fix",
                        "title": "Clarify public setup docs",
                        "summary": "Add a verification command to public setup docs.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_cli(
        "discover",
        "--source",
        "json",
        "--input",
        str(source),
        "--out",
        str(out),
        "--summary-json",
    )

    assert out.exists()
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "ok": True,
        "output": str(out),
        "total": 1,
        "ids": ["user-docs-fix"],
    }
    assert result.stdout == (
        f'{{"ok":true,"output":"{out}","total":1,"ids":["user-docs-fix"]}}\n'
    )


def test_cli_discover_json_reads_opportunities_from_stdin_dash_with_summary_json(
    tmp_path: Path,
) -> None:
    out = tmp_path / "discovered.json"

    result = run_cli(
        "discover",
        "--source",
        "json",
        "--input",
        "-",
        "--out",
        str(out),
        "--summary-json",
        input=stdin_opportunities_json("stdin-docs-fix"),
    )

    assert read_json(out)[0]["id"] == "stdin-docs-fix"
    assert result.stderr == ""
    assert result.stdout == (
        f'{{"ok":true,"output":"{out}","total":1,"ids":["stdin-docs-fix"]}}\n'
    )


def test_cli_validate_reports_opportunity_count_and_ids(tmp_path: Path) -> None:
    source = tmp_path / "opportunities.json"
    source.write_text(
        json.dumps(
            {
                "opportunities": [
                    {
                        "id": "user-docs-fix",
                        "title": "Clarify public setup docs",
                        "summary": "Add a verification command to public setup docs.",
                    },
                    {
                        "id": "user-test-fix",
                        "title": "Fix flaky public test",
                        "summary": "Stabilize a deterministic unit test.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_cli("validate", str(source))

    assert result.stdout == "Validated 2 opportunities: user-docs-fix, user-test-fix\n"
    assert result.stderr == ""


def test_cli_validate_json_reports_success_payload(tmp_path: Path) -> None:
    source = tmp_path / "opportunities.json"
    source.write_text(
        json.dumps(
            {
                "opportunities": [
                    {
                        "id": "user-docs-fix",
                        "title": "Clarify public setup docs",
                        "summary": "Add a verification command to public setup docs.",
                    },
                    {
                        "id": "user-test-fix",
                        "title": "Fix flaky public test",
                        "summary": "Stabilize a deterministic unit test.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_cli("validate", "--json", str(source))

    assert result.stdout == '{"ids":["user-docs-fix","user-test-fix"],"ok":true,"total":2}\n'
    assert json.loads(result.stdout) == {
        "total": 2,
        "ids": ["user-docs-fix", "user-test-fix"],
        "ok": True,
    }
    assert result.stderr == ""


def test_cli_validate_json_reads_opportunities_from_stdin_dash() -> None:
    result = run_cli(
        "validate",
        "--json",
        "-",
        input=stdin_opportunities_json("stdin-docs-fix", "stdin-test-fix"),
    )

    assert result.stdout == '{"ids":["stdin-docs-fix","stdin-test-fix"],"ok":true,"total":2}\n'
    assert result.stderr == ""


def test_cli_validate_json_reports_invalid_json_as_json(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    source.write_text('{"opportunities": [', encoding="utf-8")

    result = run_cli_unchecked("validate", "--json", str(source))

    assert result.returncode != 0
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "input file is not valid JSON" in payload["error"]
    assert result.stdout == json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"


def test_cli_validate_json_reports_schema_errors_as_json(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    source.write_text(
        '{"opportunities": [{"title": "Missing id", "summary": "No id."}]}',
        encoding="utf-8",
    )

    result = run_cli_unchecked("validate", "--json", str(source))

    assert result.returncode != 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "ok": False,
        "error": "opportunities[0].id is required and must be a non-empty string",
    }


def test_cli_validate_json_rejects_duplicate_ids(tmp_path: Path) -> None:
    source = tmp_path / "duplicates.json"
    source.write_text(
        stdin_opportunities_json("duplicate-id", "duplicate-id"),
        encoding="utf-8",
    )

    result = run_cli_unchecked("validate", "--json", str(source))

    assert result.returncode != 0
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert 'duplicate id "duplicate-id"' in payload["error"]
    assert "opportunities[0].id" in payload["error"]
    assert "opportunities[1].id" in payload["error"]
    assert "earlier index 0" in payload["error"]
    assert "later index 1" in payload["error"]


def test_minimal_example_validates_and_imports_through_cli(tmp_path: Path) -> None:
    out = tmp_path / "discovered.json"

    validate_result = run_cli("validate", "examples/minimal-opportunities.json")
    run_cli(
        "discover",
        "--source",
        "json",
        "--input",
        "examples/minimal-opportunities.json",
        "--out",
        str(out),
    )

    opportunities = read_json(out)
    assert validate_result.stdout == "Validated 1 opportunity: docs-install-check\n"
    assert validate_result.stderr == ""
    assert len(opportunities) == 1
    assert opportunities[0]["id"] == "docs-install-check"
    assert opportunities[0]["source"] == "json"
    assert opportunities[0]["reward"] == {"amount": 0, "currency": "USD", "type": "unknown"}


def test_cli_validate_reports_field_level_validation_errors(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    source.write_text('{"opportunities": [{"title": "Missing id", "summary": "No id."}]}', encoding="utf-8")

    result = run_cli_unchecked("validate", str(source))

    assert result.returncode == 2
    assert "opportunities[0].id is required" in result.stderr


def test_cli_json_source_requires_input(tmp_path: Path) -> None:
    out = tmp_path / "discovered.json"

    result = run_cli_unchecked("discover", "--source", "json", "--out", str(out))

    assert result.returncode == 2
    assert "--source json requires --input PATH" in result.stderr
    assert not out.exists()


def test_cli_json_import_reports_validation_errors(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    out = tmp_path / "discovered.json"
    source.write_text('{"opportunities": [{"title": "Missing id", "summary": "No id."}]}', encoding="utf-8")

    result = run_cli_unchecked(
        "discover", "--source", "json", "--input", str(source), "--out", str(out)
    )

    assert result.returncode == 2
    assert "opportunities[0].id is required" in result.stderr
    assert not out.exists()


def test_cli_json_import_rejects_duplicate_ids(tmp_path: Path) -> None:
    source = tmp_path / "duplicates.json"
    out = tmp_path / "discovered.json"
    source.write_text(
        stdin_opportunities_json("duplicate-id", "duplicate-id"),
        encoding="utf-8",
    )

    result = run_cli_unchecked(
        "discover", "--source", "json", "--input", str(source), "--out", str(out)
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert 'duplicate id "duplicate-id"' in result.stderr
    assert "opportunities[0].id" in result.stderr
    assert "opportunities[1].id" in result.stderr
    assert not out.exists()


def test_cli_score_missing_input_fails_without_output(tmp_path: Path) -> None:
    out = tmp_path / "scored.json"
    missing = tmp_path / "missing.json"

    result = run_cli_unchecked("score", str(missing), "--out", str(out))

    assert result.returncode == 2
    assert result.stdout == ""
    assert "bounty-sieve score: error: input file not found:" in result.stderr
    assert "Traceback" not in result.stderr
    assert not out.exists()


def test_cli_score_invalid_json_fails_without_traceback(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    out = tmp_path / "scored.json"
    source.write_text("{not json", encoding="utf-8")

    result = run_cli_unchecked("score", str(source), "--out", str(out))

    assert result.returncode == 2
    assert result.stdout == ""
    assert "bounty-sieve score: error: input file is not valid JSON:" in result.stderr
    assert "Traceback" not in result.stderr
    assert not out.exists()


def test_cli_score_reports_field_level_validation_errors_without_output(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    out = tmp_path / "scored.json"
    source.write_text('{"opportunities": [{"title": "Missing id", "summary": "No id."}]}', encoding="utf-8")

    result = run_cli_unchecked("score", str(source), "--out", str(out))

    assert result.returncode == 2
    assert result.stdout == ""
    assert "opportunities[0].id is required" in result.stderr
    assert "Traceback" not in result.stderr
    assert not out.exists()


def test_cli_score_unusable_opportunity_list_fails_without_traceback(
    tmp_path: Path,
) -> None:
    source = tmp_path / "bad.json"
    out = tmp_path / "scored.json"
    source.write_text('{"items": []}', encoding="utf-8")

    result = run_cli_unchecked("score", str(source), "--out", str(out))

    assert result.returncode == 2
    assert result.stdout == ""
    assert 'top-level JSON must be a list or an object with an "opportunities" list' in result.stderr
    assert "Traceback" not in result.stderr
    assert not out.exists()


def test_cli_score_rejects_duplicate_ids_before_writing(tmp_path: Path) -> None:
    source = tmp_path / "duplicates.json"
    out = tmp_path / "scored.json"
    source.write_text(
        stdin_opportunities_json("duplicate-id", "duplicate-id"),
        encoding="utf-8",
    )

    result = run_cli_unchecked("score", str(source), "--out", str(out))

    assert result.returncode == 2
    assert result.stdout == ""
    assert 'duplicate id "duplicate-id"' in result.stderr
    assert "opportunities[0].id" in result.stderr
    assert "opportunities[1].id" in result.stderr
    assert "Traceback" not in result.stderr
    assert not out.exists()


def test_fixture_discovery_writes_realistic_fixture_set(tmp_path: Path) -> None:
    out = tmp_path / "opportunities.json"

    run_cli("discover", "--source", "fixture", "--out", str(out))

    opportunities = read_json(out)
    ids = {item["id"] for item in opportunities}
    assert len(opportunities) == 7
    assert "safe-docs-quickstart" in ids
    assert "reject-prompt-exfiltration" in ids
    assert "reject-star-gated-bounty" in ids
    assert "reject-unknown-token" in ids
    assert "watch-duplicate-pr-swarm" in ids
    assert "watch-vague-high-complexity" in ids


def test_sample_opportunities_json_imports_and_scores(tmp_path: Path) -> None:
    discovered = tmp_path / "discovered.json"
    scored = tmp_path / "scored.json"

    run_cli(
        "discover",
        "--source",
        "json",
        "--input",
        "examples/opportunities.sample.json",
        "--out",
        str(discovered),
    )
    run_cli("score", str(discovered), "--out", str(scored))

    opportunities = read_json(discovered)
    recommendations = {item["id"]: item["score"]["recommendation"] for item in read_json(scored)}
    assert len(opportunities) == 4
    assert recommendations["docs-install-check"] == "pursue"
    assert recommendations["json-export-edge-case"] == "pursue"
    assert recommendations["watch-vague-performance"] == "watch"
    assert recommendations["reject-wallet-connection"] == "reject"


def test_score_default_stdout_stays_silent(tmp_path: Path) -> None:
    discovered = tmp_path / "opportunities.json"
    scored = tmp_path / "scored.json"
    run_cli("discover", "--source", "fixture", "--out", str(discovered))

    result = run_cli("score", str(discovered), "--out", str(scored))

    assert scored.exists()
    assert result.stdout == ""
    assert result.stderr == ""


def test_score_without_out_prints_compact_json_to_stdout(tmp_path: Path) -> None:
    discovered = tmp_path / "opportunities.json"
    run_cli("discover", "--source", "fixture", "--out", str(discovered))

    result = run_cli("score", str(discovered))

    payload = json.loads(result.stdout)
    assert result.stderr == ""
    assert len(payload) == 7
    assert {item["score"]["recommendation"] for item in payload} == {
        "pursue",
        "watch",
        "reject",
    }
    assert "\n" not in result.stdout.rstrip("\n")
    assert '": ' not in result.stdout
    assert ', "' not in result.stdout


def test_score_stdin_dash_without_out_prints_compact_json_to_stdout() -> None:
    result = run_cli(
        "score",
        "-",
        input=stdin_opportunities_json("stdin-docs-fix"),
    )

    payload = json.loads(result.stdout)
    assert result.stderr == ""
    assert len(payload) == 1
    assert payload[0]["id"] == "stdin-docs-fix"
    assert "score" in payload[0]
    assert "\n" not in result.stdout.rstrip("\n")
    assert '": ' not in result.stdout
    assert ', "' not in result.stdout


def test_score_without_out_does_not_write_output_file(tmp_path: Path) -> None:
    discovered = tmp_path / "opportunities.json"
    run_cli("discover", "--source", "fixture", "--out", str(discovered))

    result = run_cli("score", str(discovered))

    assert result.stderr == ""
    assert sorted(path.name for path in tmp_path.iterdir()) == ["opportunities.json"]


def test_compare_human_stdout_reports_recommendation_and_roi_diffs(
    tmp_path: Path,
) -> None:
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before_json, after_json = compare_before_after_json()
    before.write_text(before_json, encoding="utf-8")
    after.write_text(after_json, encoding="utf-8")

    result = run_cli("compare", str(before), str(after))

    assert result.stderr == ""
    assert "# Bounty Sieve Compare" in result.stdout
    assert "## Safety Boundary" in result.stdout
    assert "performs no network access" in result.stdout
    assert "requests no credentials" in result.stdout
    assert "- Before total: 4" in result.stdout
    assert "- After total: 4" in result.stdout
    assert "- Added: 1" in result.stdout
    assert "- Removed: 1" in result.stdout
    assert "- Changed recommendation: 1" in result.stdout
    assert "- Changed ROI score: 2" in result.stdout
    assert "- Unchanged: 1" in result.stdout
    assert "- added-task: recommendation=watch, roi_score=" in result.stdout
    assert "- removed-task: recommendation=pursue, roi_score=" in result.stdout
    assert "- rec-change: recommendation watch -> pursue" in result.stdout
    assert "- roi-change: recommendation pursue -> pursue" in result.stdout
    assert "Added task title" not in result.stdout
    assert "ROI change summary" not in result.stdout
    assert sorted(path.name for path in tmp_path.iterdir()) == ["after.json", "before.json"]


def test_compare_json_output_shape(tmp_path: Path) -> None:
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before_json, after_json = compare_before_after_json()
    before.write_text(before_json, encoding="utf-8")
    after.write_text(after_json, encoding="utf-8")

    result = run_cli("compare", str(before), str(after), "--json")

    payload = json.loads(result.stdout)
    assert result.stderr == ""
    assert payload["ok"] is True
    assert payload["before_total"] == 4
    assert payload["after_total"] == 4
    assert payload["counts"] == {
        "added": 1,
        "removed": 1,
        "changed_recommendation": 1,
        "changed_roi_score": 2,
        "unchanged": 1,
    }
    assert payload["added"][0]["id"] == "added-task"
    assert payload["removed"][0]["id"] == "removed-task"
    assert [item["id"] for item in payload["changed_recommendation"]] == ["rec-change"]
    assert [item["id"] for item in payload["changed_roi_score"]] == [
        "rec-change",
        "roi-change",
    ]
    rec_change = payload["changed_recommendation"][0]
    assert rec_change["before"]["recommendation"] == "watch"
    assert rec_change["after"]["recommendation"] == "pursue"
    assert "safety_boundary" in payload
    assert "Added task title" not in result.stdout
    assert "\n" not in result.stdout.rstrip("\n")


def test_compare_out_writes_markdown_or_json_without_stdout(tmp_path: Path) -> None:
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    markdown_out = tmp_path / "compare.md"
    json_out = tmp_path / "compare.json"
    before_json, after_json = compare_before_after_json()
    before.write_text(before_json, encoding="utf-8")
    after.write_text(after_json, encoding="utf-8")

    markdown_result = run_cli("compare", str(before), str(after), "--out", str(markdown_out))
    json_result = run_cli(
        "compare", str(before), str(after), "--json", "--out", str(json_out)
    )

    markdown = markdown_out.read_text(encoding="utf-8")
    payload = read_json(json_out)
    assert markdown_result.stdout == ""
    assert markdown_result.stderr == ""
    assert "# Bounty Sieve Compare" in markdown
    assert "- Changed recommendation: 1" in markdown
    assert json_result.stdout == ""
    assert json_result.stderr == ""
    assert payload["ok"] is True
    assert payload["counts"]["changed_roi_score"] == 2


def test_rank_table_sorts_by_recommendation_then_roi_and_respects_limit(
    tmp_path: Path,
) -> None:
    source = tmp_path / "opportunities.json"
    source.write_text(
        json.dumps(
            {
                "opportunities": [
                    {
                        "id": "watch-complex",
                        "title": "High reward but complex backend refactor",
                        "summary": "Large task with a fixed reward.",
                        "url": "https://github.com/example/app/issues/3",
                        "reward": {"amount": 1000, "currency": "USD", "type": "fixed"},
                        "signals": {
                            "clarity": "high",
                            "repo_activity": "active",
                            "competition": "low",
                            "complexity": "high",
                            "scope": "large",
                            "tech": ["python"],
                        },
                    },
                    {
                        "id": "pursue-lower-roi",
                        "title": "Fix flaky CLI test",
                        "summary": "Small deterministic test repair.",
                        "url": "https://github.com/example/app/issues/2",
                        "reward": {"amount": 150, "currency": "USD", "type": "fixed"},
                        "signals": {
                            "clarity": "medium",
                            "repo_activity": "active",
                            "competition": "low",
                            "complexity": "low",
                            "scope": "small",
                            "tech": ["python"],
                        },
                    },
                    {
                        "id": "pursue-higher-roi",
                        "title": "Fix docs quickstart",
                        "summary": "Tiny docs task with clear acceptance criteria.",
                        "url": "https://github.com/example/app/issues/1",
                        "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                        "signals": {
                            "clarity": "high",
                            "repo_activity": "active",
                            "competition": "low",
                            "complexity": "low",
                            "scope": "tiny",
                            "tech": ["markdown", "cli"],
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_cli("rank", str(source), "--limit", "2")

    lines = result.stdout.splitlines()
    rows = lines[2:]
    assert result.stderr == ""
    assert lines[0].startswith("Recommendation")
    assert "ROI" in lines[0]
    assert "Reward" in lines[0]
    assert "Title" in lines[0]
    assert "URL" in lines[0]
    assert len(rows) == 2
    assert rows[0].startswith("pursue")
    assert "Fix docs quickstart" in rows[0]
    assert "https://github.com/example/app/issues/1" in rows[0]
    assert rows[1].startswith("pursue")
    assert "Fix flaky CLI test" in rows[1]
    assert "https://github.com/example/app/issues/2" in rows[1]
    assert "High reward but complex backend refactor" not in result.stdout


def test_rank_json_output_shape(tmp_path: Path) -> None:
    source = tmp_path / "opportunities.json"
    source.write_text(
        json.dumps(
            {
                "opportunities": [
                    {
                        "id": "watch-vague",
                        "title": "Investigate vague performance issue",
                        "summary": "Unclear performance work.",
                        "url": "https://github.com/example/app/issues/2",
                        "signals": {"clarity": "low"},
                    },
                    {
                        "id": "pursue-docs",
                        "title": "Fix docs quickstart",
                        "summary": "Tiny docs task.",
                        "url": "https://github.com/example/app/issues/1",
                        "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                        "signals": {
                            "clarity": "high",
                            "repo_activity": "active",
                            "competition": "low",
                            "complexity": "low",
                            "scope": "tiny",
                            "tech": ["markdown"],
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_cli("rank", str(source), "--limit", "1", "--json")

    payload = json.loads(result.stdout)
    assert result.stderr == ""
    assert payload["ok"] is True
    assert payload["total"] == 2
    assert payload["shown"] == 1
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert set(item) == {
        "id",
        "title",
        "url",
        "recommendation",
        "roi_score",
        "reward_estimate_usd",
        "reasons",
        "actionability",
    }
    assert item["id"] == "pursue-docs"
    assert item["title"] == "Fix docs quickstart"
    assert item["url"] == "https://github.com/example/app/issues/1"
    assert item["recommendation"] == "pursue"
    assert isinstance(item["roi_score"], int)
    assert item["reward_estimate_usd"] == 100
    assert isinstance(item["reasons"], list)
    assert_actionability_shape(item["actionability"])


def test_rank_rejects_non_positive_limit(tmp_path: Path) -> None:
    source = tmp_path / "opportunities.json"
    source.write_text("[]", encoding="utf-8")

    result = run_cli_unchecked("rank", str(source), "--limit", "0")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "bounty-sieve rank: error: --limit must be greater than 0" in result.stderr


def test_search_preview_help_documents_read_only_github_preview() -> None:
    result = run_cli_unchecked("search-preview", "--help")

    assert result.returncode == 0
    assert "Preview ranked public GitHub issues from a read-only search." in result.stdout
    assert "--query" in result.stdout
    assert "--limit" in result.stdout
    assert "--repo-health" in result.stdout
    assert "--json" in result.stdout


def test_search_preview_markdown_uses_importer_scores_and_writes_no_files(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    calls = []

    def fake_import(query: str, limit: int) -> list[dict]:
        calls.append((query, limit))
        return [
            {
                "id": "github-example-app-2",
                "title": "Investigate vague performance issue",
                "summary": "Unclear performance work.",
                "url": "https://github.com/example/app/issues/2",
                "platform": "github",
                "repo": "example/app",
                "source": "github-issue",
                "signals": {"clarity": "low"},
            },
            {
                "id": "github-example-app-1",
                "title": "Fix docs quickstart",
                "summary": "Tiny docs task.",
                "url": "https://github.com/example/app/issues/1",
                "platform": "github",
                "repo": "example/app",
                "source": "github-issue",
                "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                "signals": {
                    "clarity": "high",
                    "repo_activity": "active",
                    "competition": "low",
                    "complexity": "low",
                    "scope": "tiny",
                    "tech": ["markdown"],
                },
            },
        ]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("bounty_sieve.__main__.import_github_search", fake_import)

    result = cli_main(["search-preview", "--query", "bounty docs"])

    captured = capsys.readouterr()
    assert result == 0
    assert calls == [("bounty docs", 10)]
    assert captured.err == ""
    assert "# Bounty Sieve Search Preview" in captured.out
    assert "## Safety Boundary" in captured.out
    assert "read-only public GitHub API fetches" in captured.out
    assert "- Query: bounty docs" in captured.out
    assert "- Limit: 10" in captured.out
    assert "- Imported and scored: 2" in captured.out
    assert captured.out.index("Fix docs quickstart") < captured.out.index(
        "Investigate vague performance issue"
    )
    assert "- ID: github-example-app-1" in captured.out
    assert "- Recommendation: pursue" in captured.out
    assert "- ROI:" in captured.out
    assert "- Repository: example/app" in captured.out
    assert "- URL: https://github.com/example/app/issues/1" in captured.out
    assert "Manual Approval Boundary" in captured.out
    assert "not approval to clone, claim work, comment, open PRs" in captured.out
    assert list(tmp_path.iterdir()) == []


def test_search_preview_json_is_compact_ranked_and_writes_no_files(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    def fake_import(query: str, limit: int) -> list[dict]:
        assert query == 'label:"good first issue" bounty'
        assert limit == 2
        return [
            {
                "id": "github-example-app-2",
                "title": "Investigate vague performance issue",
                "summary": "Unclear performance work.",
                "url": "https://github.com/example/app/issues/2",
                "platform": "github",
                "repo": "example/app",
                "source": "github-issue",
                "signals": {"clarity": "low"},
            },
            {
                "id": "github-example-app-1",
                "title": "Fix docs quickstart",
                "summary": "Tiny docs task.",
                "url": "https://github.com/example/app/issues/1",
                "platform": "github",
                "repo": "example/app",
                "source": "github-issue",
                "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                "signals": {
                    "clarity": "high",
                    "repo_activity": "active",
                    "competition": "low",
                    "complexity": "low",
                    "scope": "tiny",
                    "tech": ["markdown"],
                },
            },
        ]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("bounty_sieve.__main__.import_github_search", fake_import)

    result = cli_main(
        [
            "search-preview",
            "--query",
            'label:"good first issue" bounty',
            "--limit",
            "2",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert result == 0
    assert captured.err == ""
    assert payload["ok"] is True
    assert payload["query"] == 'label:"good first issue" bounty'
    assert payload["total"] == 2
    assert [item["id"] for item in payload["ranked"]] == [
        "github-example-app-1",
        "github-example-app-2",
    ]
    item = payload["ranked"][0]
    assert set(item) == {
        "id",
        "title",
        "url",
        "repo",
        "recommendation",
        "roi_score",
        "reward_estimate_usd",
        "reasons",
        "actionability",
    }
    assert item["repo"] == "example/app"
    assert item["recommendation"] == "pursue"
    assert item["reward_estimate_usd"] == 100
    assert_actionability_shape(item["actionability"])
    assert "writes no files" in payload["safety_boundary"]
    assert "\n" not in captured.out.rstrip("\n")
    assert list(tmp_path.iterdir()) == []


def test_search_preview_repo_health_json_exposes_health_and_passes_flag(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    calls = []

    def fake_import(
        query: str,
        limit: int,
        include_repo_health: bool = False,
    ) -> list[dict]:
        calls.append((query, limit, include_repo_health))
        return [
            {
                "id": "github-example-app-1",
                "title": "Fix docs quickstart",
                "summary": "Tiny docs task.",
                "url": "https://github.com/example/app/issues/1",
                "platform": "github",
                "repo": "example/app",
                "source": "github-issue",
                "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                "signals": {
                    "clarity": "high",
                    "repo_activity": "low",
                    "repo_health_stale": True,
                    "repo_archived": True,
                    "competition": "low",
                    "complexity": "low",
                    "scope": "tiny",
                    "tech": ["markdown"],
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

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("bounty_sieve.__main__.import_github_search", fake_import)

    result = cli_main(
        [
            "search-preview",
            "--query",
            "bounty docs",
            "--repo-health",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    item = payload["ranked"][0]
    assert result == 0
    assert calls == [("bounty docs", 10, True)]
    assert item["recommendation"] == "watch"
    assert "watch: repository is archived" in item["reasons"]
    assert item["repo_health"] == {
        "stars": 12,
        "open_issues_count": 4,
        "archived": True,
        "pushed_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "repo_activity": "low",
        "reason": "repository is archived",
    }
    assert list(tmp_path.iterdir()) == []


def test_search_preview_repo_health_markdown_exposes_health(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    def fake_import(
        query: str,
        limit: int,
        include_repo_health: bool = False,
    ) -> list[dict]:
        assert include_repo_health is True
        return [
            {
                "id": "github-example-app-1",
                "title": "Fix docs quickstart",
                "summary": "Tiny docs task.",
                "url": "https://github.com/example/app/issues/1",
                "platform": "github",
                "repo": "example/app",
                "source": "github-issue",
                "signals": {
                    "clarity": "high",
                    "repo_activity": "active",
                    "competition": "low",
                    "complexity": "low",
                    "scope": "tiny",
                    "tech": ["markdown"],
                },
                "metadata": {
                    "github": {
                        "repo_health": {
                            "stars": 12,
                            "open_issues_count": 4,
                            "archived": False,
                            "pushed_at": "2026-05-20T00:00:00Z",
                            "updated_at": "2026-05-21T00:00:00Z",
                            "repo_activity": "active",
                            "reason": "repository pushed within 180 days",
                        }
                    }
                },
            }
        ]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("bounty_sieve.__main__.import_github_search", fake_import)

    result = cli_main(["search-preview", "--query", "bounty docs", "--repo-health"])

    captured = capsys.readouterr()
    assert result == 0
    assert "- Repo health: activity=active, archived=false, stars=12" in captured.out
    assert "open_issues=4" in captured.out
    assert "reason=repository pushed within 180 days" in captured.out
    assert list(tmp_path.iterdir()) == []


def test_search_preview_reports_import_and_validation_errors_as_argparse_errors(
    monkeypatch, capsys
) -> None:
    def fake_import_error(query: str, limit: int) -> list[dict]:
        raise GitHubImportError("GitHub fetch failed with HTTP 403")

    monkeypatch.setattr("bounty_sieve.__main__.import_github_search", fake_import_error)

    try:
        cli_main(["search-preview", "--query", "bounty"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse SystemExit")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "bounty-sieve search-preview: error: GitHub fetch failed with HTTP 403" in (
        captured.err
    )
    assert "Traceback" not in captured.err

    def fake_validation_error(query: str, limit: int) -> list[dict]:
        raise OpportunityValidationError("opportunities[0].id is required")

    monkeypatch.setattr(
        "bounty_sieve.__main__.import_github_search", fake_validation_error
    )

    try:
        cli_main(["search-preview", "--query", "bounty"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse SystemExit")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "bounty-sieve search-preview: error: opportunities[0].id is required" in (
        captured.err
    )
    assert "Traceback" not in captured.err


def test_search_preview_403_error_is_actionable_and_does_not_leak_secrets(
    monkeypatch, capsys
) -> None:
    def fake_urlopen(request, timeout):
        headers = Message()
        headers["x-ratelimit-remaining"] = "0"
        headers["x-ratelimit-reset"] = "1779883200"
        raise HTTPError(
            request.full_url,
            403,
            "Forbidden",
            headers,
            BytesIO(b'{"message":"secret-body-value should not leak"}'),
        )

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("bounty_sieve.github_importer.urlopen", fake_urlopen)

    try:
        cli_main(["search-preview", "--query", 'label:"good first issue" bounty'])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse SystemExit")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        "bounty-sieve search-preview: error: GitHub fetch failed with HTTP 403 "
        "(rate limited or forbidden)"
    ) in captured.err
    assert "GITHUB_TOKEN set: no" in captured.err
    assert "GitHub rate limit remaining: 0" in captured.err
    assert "GitHub rate limit resets at: 2026-05-27T12:00:00Z" in captured.err
    assert "narrow --query/--limit" in captured.err
    assert "set GITHUB_TOKEN for higher rate limits" in captured.err
    assert "secret-body-value" not in captured.err
    assert "Traceback" not in captured.err


def test_search_preview_rejects_invalid_limit_without_fetching_network(
    monkeypatch, capsys
) -> None:
    def fake_import(query: str, limit: int) -> list[dict]:
        raise AssertionError("search-preview should validate limit before importing")

    monkeypatch.setattr("bounty_sieve.__main__.import_github_search", fake_import)

    try:
        cli_main(["search-preview", "--query", "bounty", "--limit", "51"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse SystemExit")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "bounty-sieve search-preview: error: --limit must be between 1 and 50" in (
        captured.err
    )


def test_search_report_help_documents_one_command_workflow() -> None:
    result = run_cli_unchecked("search-report", "--help")

    assert result.returncode == 0
    assert "Search public GitHub issues, score them, and write a decision brief." in result.stdout
    assert "--query" in result.stdout
    assert "--limit" in result.stdout
    assert "--out" in result.stdout
    assert "--json-out" in result.stdout
    assert "--repo-health" in result.stdout
    assert "--summary" in result.stdout
    assert "--summary-json" in result.stdout


def test_search_report_writes_markdown_report_from_mocked_github_search(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    calls = []
    report = tmp_path / "report.md"

    def fake_import(query: str, limit: int) -> list[dict]:
        calls.append((query, limit))
        return [
            {
                "id": "github-example-app-1",
                "title": "Fix docs quickstart",
                "summary": "Tiny docs task.",
                "url": "https://github.com/example/app/issues/1",
                "platform": "github",
                "repo": "example/app",
                "source": "github-issue",
                "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                "signals": {
                    "clarity": "high",
                    "repo_activity": "active",
                    "competition": "low",
                    "complexity": "low",
                    "scope": "tiny",
                    "tech": ["markdown"],
                },
            }
        ]

    monkeypatch.setattr("bounty_sieve.__main__.import_github_search", fake_import)

    result = cli_main(["search-report", "--query", "bounty docs", "--out", str(report)])

    captured = capsys.readouterr()
    markdown = report.read_text(encoding="utf-8")
    assert result == 0
    assert calls == [("bounty docs", 10)]
    assert captured.out == ""
    assert captured.err == ""
    assert "# Bounty Sieve Decision Brief" in markdown
    assert "## Safety Boundary" in markdown
    assert "Fix docs quickstart" in markdown
    assert "- pursue: 1" in markdown
    assert "- watch: 0" in markdown
    assert "- reject: 0" in markdown
    assert not (tmp_path / "scored.json").exists()


def test_search_report_writes_optional_json_and_summary_json(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    report = tmp_path / "report.md"
    scored_json = tmp_path / "scored.json"

    def fake_import(query: str, limit: int) -> list[dict]:
        assert query == 'label:"good first issue" bounty'
        assert limit == 2
        return [
            {
                "id": "github-example-app-1",
                "title": "Fix docs quickstart",
                "summary": "Tiny docs task.",
                "url": "https://github.com/example/app/issues/1",
                "platform": "github",
                "repo": "example/app",
                "source": "github-issue",
                "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                "signals": {
                    "clarity": "high",
                    "repo_activity": "active",
                    "competition": "low",
                    "complexity": "low",
                    "scope": "tiny",
                    "tech": ["markdown"],
                },
            },
            {
                "id": "github-example-app-2",
                "title": "Investigate vague performance issue",
                "summary": "Unclear performance work.",
                "url": "https://github.com/example/app/issues/2",
                "platform": "github",
                "repo": "example/app",
                "source": "github-issue",
                "signals": {"clarity": "low"},
            },
        ]

    monkeypatch.setattr("bounty_sieve.__main__.import_github_search", fake_import)

    result = cli_main(
        [
            "search-report",
            "--query",
            'label:"good first issue" bounty',
            "--limit",
            "2",
            "--out",
            str(report),
            "--json-out",
            str(scored_json),
            "--summary-json",
        ]
    )

    captured = capsys.readouterr()
    scored = read_json(scored_json)
    summary = json.loads(captured.out)
    assert result == 0
    assert captured.err == ""
    assert report.exists()
    assert [item["id"] for item in scored] == [
        "github-example-app-1",
        "github-example-app-2",
    ]
    assert all("score" in item for item in scored)
    assert summary["report_path"] == str(report)
    assert summary["total"] == 2
    assert summary["recommendations"]["pursue"] == 1
    assert summary["summary"].startswith("Bounty Sieve reviewed 2 opportunities:")


def test_search_report_summary_prints_report_style_stdout_after_writing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    report = tmp_path / "report.md"

    def fake_import(query: str, limit: int) -> list[dict]:
        return [
            {
                "id": "github-example-app-1",
                "title": "Fix docs quickstart",
                "summary": "Tiny docs task.",
                "signals": {
                    "clarity": "high",
                    "repo_activity": "active",
                    "competition": "low",
                    "complexity": "low",
                    "scope": "tiny",
                },
            }
        ]

    monkeypatch.setattr("bounty_sieve.__main__.import_github_search", fake_import)

    result = cli_main(["search-report", "--query", "bounty docs", "--out", str(report), "--summary"])

    captured = capsys.readouterr()
    assert result == 0
    assert captured.err == ""
    assert captured.out == (
        f"Report: {report}\n"
        "Total: 1\n"
        "Recommendations: pursue=1, watch=0, reject=0\n"
        "Summary: Bounty Sieve reviewed 1 opportunities: 1 look worth manual verification, "
        "0 need caution before spending time, and 0 should be rejected under the current safety rules.\n"
    )


def test_search_report_passes_repo_health_to_github_search(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    calls = []
    report = tmp_path / "report.md"

    def fake_import(
        query: str,
        limit: int,
        include_repo_health: bool = False,
    ) -> list[dict]:
        calls.append((query, limit, include_repo_health))
        return [
            {
                "id": "github-example-app-1",
                "title": "Fix docs quickstart",
                "summary": "Tiny docs task.",
                "signals": {
                    "clarity": "high",
                    "repo_activity": "active",
                    "competition": "low",
                    "complexity": "low",
                    "scope": "tiny",
                },
            }
        ]

    monkeypatch.setattr("bounty_sieve.__main__.import_github_search", fake_import)

    result = cli_main(
        ["search-report", "--query", "bounty docs", "--repo-health", "--out", str(report)]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert calls == [("bounty docs", 10, True)]
    assert captured.out == ""
    assert captured.err == ""
    assert report.exists()


def test_search_report_reports_import_errors_without_traceback(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    report = tmp_path / "report.md"

    def fake_import_error(query: str, limit: int) -> list[dict]:
        raise GitHubImportError("GitHub fetch failed with HTTP 403")

    monkeypatch.setattr("bounty_sieve.__main__.import_github_search", fake_import_error)

    try:
        cli_main(["search-report", "--query", "bounty", "--out", str(report)])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse SystemExit")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "bounty-sieve search-report: error: GitHub fetch failed with HTTP 403" in (
        captured.err
    )
    assert "Traceback" not in captured.err
    assert not report.exists()


def test_search_report_rejects_invalid_limit_without_fetching_network(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    report = tmp_path / "report.md"

    def fake_import(query: str, limit: int) -> list[dict]:
        raise AssertionError("search-report should validate limit before importing")

    monkeypatch.setattr("bounty_sieve.__main__.import_github_search", fake_import)

    try:
        cli_main(["search-report", "--query", "bounty", "--limit", "51", "--out", str(report)])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse SystemExit")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "bounty-sieve search-report: error: --limit must be between 1 and 50" in (
        captured.err
    )
    assert not report.exists()


def test_shortlist_help_documents_export_flags() -> None:
    result = run_cli_unchecked("shortlist", "--help")

    assert result.returncode == 0
    assert "Export a local read-only shortlist" in result.stdout
    assert "--limit" in result.stdout
    assert "--recommendation" in result.stdout
    assert "--format" in result.stdout
    assert "--out" in result.stdout


def test_shortlist_markdown_stdout_is_clean_and_does_not_write_dash_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "opportunities.json"
    source.write_text(shortlist_opportunities_json(), encoding="utf-8")

    result = run_cli("shortlist", str(source), "--limit", "1", "--out", "-", cwd=tmp_path)

    assert result.stderr == ""
    assert "# Bounty Sieve Shortlist" in result.stdout
    assert "## Safety Boundary" in result.stdout
    assert "Selected: 1 of 4 total opportunities" in result.stdout
    assert "Recommendation filter: pursue" in result.stdout
    assert "Fix docs quickstart" in result.stdout
    assert "ID: pursue-higher-roi" in result.stdout
    assert "URL: https://github.com/example/app/issues/1" in result.stdout
    assert "Recommendation: pursue" in result.stdout
    assert "ROI:" in result.stdout
    assert "Reward: $100" in result.stdout
    assert "Reasons:" in result.stdout
    assert "## Manual Verification Checklist" in result.stdout
    assert "This file is only a local review shortlist" in result.stdout
    assert "Fix flaky CLI test" not in result.stdout
    assert not (tmp_path / "-").exists()


def test_shortlist_markdown_file_writes_without_stdout(tmp_path: Path) -> None:
    source = tmp_path / "opportunities.json"
    out = tmp_path / "shortlist.md"
    source.write_text(shortlist_opportunities_json(), encoding="utf-8")

    result = run_cli("shortlist", str(source), "--limit", "2", "--out", str(out))

    markdown = out.read_text(encoding="utf-8")
    assert result.stdout == ""
    assert result.stderr == ""
    assert "# Bounty Sieve Shortlist" in markdown
    assert "Selected: 2 of 4 total opportunities" in markdown
    assert markdown.index("Fix docs quickstart") < markdown.index("Fix flaky CLI test")
    assert "High reward but complex backend refactor" not in markdown


def test_shortlist_json_output_shape(tmp_path: Path) -> None:
    source = tmp_path / "opportunities.json"
    source.write_text(shortlist_opportunities_json(), encoding="utf-8")

    result = run_cli(
        "shortlist",
        str(source),
        "--limit",
        "2",
        "--format",
        "json",
        "--out",
        "-",
        cwd=tmp_path,
    )

    payload = json.loads(result.stdout)
    assert result.stderr == ""
    assert payload["ok"] is True
    assert payload["total"] == 4
    assert payload["selected"] == 2
    assert "does not clone repositories" in payload["safety_boundary"]
    assert len(payload["manual_verification_checklist"]) == 3
    assert [item["id"] for item in payload["items"]] == [
        "pursue-higher-roi",
        "pursue-lower-roi",
    ]
    assert set(payload["items"][0]) == {
        "id",
        "title",
        "url",
        "recommendation",
        "roi_score",
        "reward_estimate_usd",
        "reasons",
        "actionability",
    }
    assert payload["items"][0]["title"] == "Fix docs quickstart"
    assert payload["items"][0]["recommendation"] == "pursue"
    assert payload["items"][0]["reward_estimate_usd"] == 100
    assert isinstance(payload["items"][0]["roi_score"], int)
    assert_actionability_shape(payload["items"][0]["actionability"])
    assert not (tmp_path / "-").exists()
    assert "\n" not in result.stdout.rstrip("\n")


def test_shortlist_recommendation_filter_accepts_repeated_and_comma_values(
    tmp_path: Path,
) -> None:
    source = tmp_path / "opportunities.json"
    out = tmp_path / "shortlist.json"
    source.write_text(shortlist_opportunities_json(), encoding="utf-8")

    result = run_cli(
        "shortlist",
        str(source),
        "--recommendation",
        "watch,reject",
        "--recommendation",
        "pursue",
        "--limit",
        "3",
        "--format",
        "json",
        "--out",
        str(out),
    )

    payload = read_json(out)
    assert result.stdout == ""
    assert result.stderr == ""
    assert payload["selected"] == 3
    assert [item["id"] for item in payload["items"]] == [
        "pursue-higher-roi",
        "pursue-lower-roi",
        "watch-complex",
    ]


def test_shortlist_rejects_invalid_limit_and_recommendation(tmp_path: Path) -> None:
    source = tmp_path / "opportunities.json"
    source.write_text("[]", encoding="utf-8")

    limit_result = run_cli_unchecked("shortlist", str(source), "--limit", "0", "--out", "-")
    recommendation_result = run_cli_unchecked(
        "shortlist", str(source), "--recommendation", "maybe", "--out", "-"
    )

    assert limit_result.returncode == 2
    assert limit_result.stdout == ""
    assert "--limit must be greater than 0" in limit_result.stderr
    assert recommendation_result.returncode == 2
    assert recommendation_result.stdout == ""
    assert "--recommendation must be one of: pursue, watch, reject; got: maybe" in (
        recommendation_result.stderr
    )


def test_next_human_output_prints_best_ranked_opportunity(tmp_path: Path) -> None:
    source = tmp_path / "opportunities.json"
    source.write_text(
        json.dumps(
            {
                "opportunities": [
                    {
                        "id": "watch-complex",
                        "title": "High reward but complex backend refactor",
                        "summary": "Large task with a fixed reward.",
                        "url": "https://github.com/example/app/issues/3",
                        "reward": {"amount": 1000, "currency": "USD", "type": "fixed"},
                        "signals": {
                            "clarity": "high",
                            "repo_activity": "active",
                            "competition": "low",
                            "complexity": "high",
                            "scope": "large",
                            "tech": ["python"],
                        },
                    },
                    {
                        "id": "pursue-lower-roi",
                        "title": "Fix flaky CLI test",
                        "summary": "Small deterministic test repair.",
                        "url": "https://github.com/example/app/issues/2",
                        "reward": {"amount": 150, "currency": "USD", "type": "fixed"},
                        "signals": {
                            "clarity": "medium",
                            "repo_activity": "active",
                            "competition": "low",
                            "complexity": "low",
                            "scope": "small",
                            "tech": ["python"],
                        },
                    },
                    {
                        "id": "pursue-higher-roi",
                        "title": "Fix docs quickstart",
                        "summary": "Tiny docs task with clear acceptance criteria.",
                        "url": "https://github.com/example/app/issues/1",
                        "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                        "signals": {
                            "clarity": "high",
                            "repo_activity": "active",
                            "competition": "low",
                            "complexity": "low",
                            "scope": "tiny",
                            "tech": ["markdown", "cli"],
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_cli("next", str(source))

    assert result.stderr == ""
    assert "Next opportunity: Fix docs quickstart" in result.stdout
    assert "ID: pursue-higher-roi" in result.stdout
    assert "Recommendation: pursue" in result.stdout
    assert "Reward: $100" in result.stdout
    assert "URL: https://github.com/example/app/issues/1" in result.stdout
    assert "Reasons:" in result.stdout
    assert "Fix flaky CLI test" not in result.stdout
    assert "High reward but complex backend refactor" not in result.stdout


def test_next_json_output_shape(tmp_path: Path) -> None:
    source = tmp_path / "opportunities.json"
    source.write_text(
        json.dumps(
            {
                "opportunities": [
                    {
                        "id": "watch-vague",
                        "title": "Investigate vague performance issue",
                        "summary": "Unclear performance work.",
                        "url": "https://github.com/example/app/issues/2",
                        "signals": {"clarity": "low"},
                    },
                    {
                        "id": "pursue-docs",
                        "title": "Fix docs quickstart",
                        "summary": "Tiny docs task.",
                        "url": "https://github.com/example/app/issues/1",
                        "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                        "signals": {
                            "clarity": "high",
                            "repo_activity": "active",
                            "competition": "low",
                            "complexity": "low",
                            "scope": "tiny",
                            "tech": ["markdown"],
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_cli("next", str(source), "--json")

    payload = json.loads(result.stdout)
    assert result.stderr == ""
    assert payload["ok"] is True
    assert payload["total"] == 2
    assert set(payload["item"]) == {
        "id",
        "title",
        "url",
        "recommendation",
        "roi_score",
        "reward_estimate_usd",
        "reasons",
        "actionability",
    }
    assert payload["item"]["id"] == "pursue-docs"
    assert payload["item"]["title"] == "Fix docs quickstart"
    assert payload["item"]["recommendation"] == "pursue"
    assert payload["item"]["reward_estimate_usd"] == 100
    assert isinstance(payload["item"]["reasons"], list)
    assert_actionability_shape(payload["item"]["actionability"])


def test_next_empty_input_prints_no_op_message(tmp_path: Path) -> None:
    source = tmp_path / "opportunities.json"
    source.write_text('{"opportunities": []}', encoding="utf-8")

    result = run_cli("next", str(source))

    assert result.stderr == ""
    assert result.stdout == "No opportunities found. Add opportunities first, then rerun next.\n"


def test_explain_help_documents_read_only_decision_card() -> None:
    result = run_cli_unchecked("explain", "--help")

    assert result.returncode == 0
    assert "Print a read-only decision card for one opportunity." in result.stdout
    assert "opportunity_id" in result.stdout
    assert "--json" in result.stdout


def test_explain_human_output_prints_decision_card_without_writing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "opportunities.json"
    source.write_text(
        json.dumps(
            {
                "opportunities": [
                    {
                        "id": "pursue-docs",
                        "title": "Fix docs quickstart",
                        "summary": "Tiny docs task.",
                        "url": "https://github.com/example/app/issues/1",
                        "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                        "signals": {
                            "clarity": "high",
                            "repo_activity": "active",
                            "competition": "low",
                            "complexity": "low",
                            "scope": "tiny",
                            "tech": ["markdown", "cli"],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_cli("explain", str(source), "pursue-docs")

    assert result.stderr == ""
    assert "Decision card: Fix docs quickstart" in result.stdout
    assert "ID: pursue-docs" in result.stdout
    assert "Recommendation: pursue" in result.stdout
    assert "ROI:" in result.stdout
    assert "Reward: $100" in result.stdout
    assert "Public URL: https://github.com/example/app/issues/1" in result.stdout
    assert "Score components:" in result.stdout
    assert "- payment_confidence: 85" in result.stdout
    assert "- issue_clarity: 90" in result.stdout
    assert "Reasons:" in result.stdout
    assert "Manual verification checklist:" in result.stdout
    assert "Safety boundary:" in result.stdout
    assert "performs no network access, writes no files" in result.stdout
    assert sorted(path.name for path in tmp_path.iterdir()) == ["opportunities.json"]


def test_explain_json_output_shape(tmp_path: Path) -> None:
    source = tmp_path / "opportunities.json"
    source.write_text(
        json.dumps(
            {
                "opportunities": [
                    {
                        "id": "watch-vague",
                        "title": "Investigate vague performance issue",
                        "summary": "Unclear performance work.",
                        "signals": {"clarity": "low"},
                    },
                    {
                        "id": "pursue-docs",
                        "title": "Fix docs quickstart",
                        "summary": "Tiny docs task.",
                        "url": "https://github.com/example/app/issues/1",
                        "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
                        "signals": {
                            "clarity": "high",
                            "repo_activity": "active",
                            "competition": "low",
                            "complexity": "low",
                            "scope": "tiny",
                            "tech": ["markdown"],
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_cli("explain", str(source), "pursue-docs", "--json")

    payload = json.loads(result.stdout)
    item = payload["item"]
    assert result.stderr == ""
    assert payload["ok"] is True
    assert payload["total"] == 2
    assert set(item) == {
        "id",
        "title",
        "url",
        "recommendation",
        "roi_score",
        "reward_estimate_usd",
        "score_components",
        "reasons",
        "manual_verification_checklist",
        "safety_boundary",
        "actionability",
    }
    assert item["id"] == "pursue-docs"
    assert item["title"] == "Fix docs quickstart"
    assert item["url"] == "https://github.com/example/app/issues/1"
    assert item["recommendation"] == "pursue"
    assert item["reward_estimate_usd"] == 100
    assert isinstance(item["roi_score"], int)
    assert item["score_components"] == {
        "payment_confidence": 85,
        "issue_clarity": 90,
        "repo_activity": 85,
        "competition_risk": 20,
        "complexity_estimate": 20,
        "tech_match": 55,
        "scope_risk": 15,
    }
    assert isinstance(item["reasons"], list)
    assert_actionability_shape(item["actionability"])
    assert len(item["manual_verification_checklist"]) == 3
    assert "performs no network access, writes no files" in item["safety_boundary"]


def test_explain_not_found_reports_available_ids_without_traceback(
    tmp_path: Path,
) -> None:
    source = tmp_path / "opportunities.json"
    source.write_text(stdin_opportunities_json("docs-fix", "test-fix"), encoding="utf-8")

    result = run_cli_unchecked("explain", str(source), "missing-id")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Opportunity id not found: missing-id" in result.stderr
    assert "Available IDs: docs-fix, test-fix" in result.stderr
    assert "Traceback" not in result.stderr


def test_explain_not_found_json_reports_machine_readable_error(
    tmp_path: Path,
) -> None:
    source = tmp_path / "opportunities.json"
    source.write_text(stdin_opportunities_json("docs-fix", "test-fix"), encoding="utf-8")

    result = run_cli_unchecked("explain", str(source), "missing-id", "--json")

    assert result.returncode == 1
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "ok": False,
        "error": "opportunity id not found: missing-id",
        "id": "missing-id",
        "available_ids": ["docs-fix", "test-fix"],
    }


def test_score_summary_prints_concise_stdout_after_writing(tmp_path: Path) -> None:
    discovered = tmp_path / "opportunities.json"
    scored = tmp_path / "scored.json"
    run_cli("discover", "--source", "fixture", "--out", str(discovered))

    result = run_cli("score", str(discovered), "--out", str(scored), "--summary")

    assert scored.exists()
    assert result.stderr == ""
    assert result.stdout == (
        f"Output: {scored}\n"
        "Total: 7\n"
        "Recommendations: pursue=2, watch=2, reject=3\n"
        "Summary: Bounty Sieve reviewed 7 opportunities: 2 look worth manual verification, "
        "2 need caution before spending time, and 3 should be rejected under the current safety rules.\n"
    )


def test_score_summary_json_prints_machine_readable_stdout_after_writing(
    tmp_path: Path,
) -> None:
    discovered = tmp_path / "opportunities.json"
    scored = tmp_path / "scored.json"
    run_cli("discover", "--source", "fixture", "--out", str(discovered))

    result = run_cli("score", str(discovered), "--out", str(scored), "--summary-json")

    assert scored.exists()
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "ok": True,
        "output": str(scored),
        "total": 7,
        "recommendations": {"pursue": 2, "watch": 2, "reject": 3},
        "summary": (
            "Bounty Sieve reviewed 7 opportunities: 2 look worth manual verification, "
            "2 need caution before spending time, and 3 should be rejected under the current safety rules."
        ),
    }
    assert result.stdout == (
        f'{{"ok":true,"output":"{scored}","total":7,'
        '"recommendations":{"pursue":2,"watch":2,"reject":3},'
        '"summary":"Bounty Sieve reviewed 7 opportunities: 2 look worth manual verification, '
        '2 need caution before spending time, and 3 should be rejected under the current safety rules."}\n'
    )


def test_score_summary_flags_are_mutually_exclusive(tmp_path: Path) -> None:
    discovered = tmp_path / "opportunities.json"
    scored = tmp_path / "scored.json"
    discovered.write_text("[]", encoding="utf-8")

    result = run_cli_unchecked(
        "score", str(discovered), "--out", str(scored), "--summary", "--summary-json"
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "not allowed with argument --summary" in result.stderr
    assert not scored.exists()


def test_score_summary_requires_out(tmp_path: Path) -> None:
    discovered = tmp_path / "opportunities.json"
    discovered.write_text("[]", encoding="utf-8")

    result = run_cli_unchecked("score", str(discovered), "--summary")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "--summary and --summary-json require --out" in result.stderr
    assert sorted(path.name for path in tmp_path.iterdir()) == ["opportunities.json"]


def test_score_summary_json_requires_out(tmp_path: Path) -> None:
    discovered = tmp_path / "opportunities.json"
    discovered.write_text("[]", encoding="utf-8")

    result = run_cli_unchecked("score", str(discovered), "--summary-json")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "--summary and --summary-json require --out" in result.stderr
    assert sorted(path.name for path in tmp_path.iterdir()) == ["opportunities.json"]


def test_scoring_rules_are_deterministic_and_transparent(tmp_path: Path) -> None:
    discovered = tmp_path / "opportunities.json"
    scored_path = tmp_path / "scored.json"
    run_cli("discover", "--source", "fixture", "--out", str(discovered))

    run_cli("score", str(discovered), "--out", str(scored_path))
    first = read_json(scored_path)
    run_cli("score", str(discovered), "--out", str(scored_path))
    second = read_json(scored_path)

    assert first == second
    by_id = {item["id"]: item["score"] for item in first}
    assert by_id["safe-docs-quickstart"]["recommendation"] == "pursue"
    assert by_id["safe-test-fix"]["recommendation"] == "pursue"
    assert by_id["reject-prompt-exfiltration"]["recommendation"] == "reject"
    assert by_id["reject-star-gated-bounty"]["recommendation"] == "reject"
    assert by_id["reject-unknown-token"]["recommendation"] == "reject"
    assert by_id["watch-duplicate-pr-swarm"]["recommendation"] == "watch"
    assert by_id["watch-vague-high-complexity"]["recommendation"] == "watch"
    assert by_id["safe-docs-quickstart"]["roi_score"] > by_id["watch-duplicate-pr-swarm"]["roi_score"]

    required_fields = {
        "reward_estimate_usd",
        "payment_confidence",
        "issue_clarity",
        "repo_activity",
        "competition_risk",
        "complexity_estimate",
        "tech_match",
        "scope_risk",
        "roi_score",
        "recommendation",
        "reasons",
        "actionability",
    }
    assert set(by_id["safe-docs-quickstart"]) == required_fields
    assert_actionability_shape(by_id["safe-docs-quickstart"]["actionability"])


def test_report_rendering_includes_required_sections(tmp_path: Path) -> None:
    discovered = tmp_path / "opportunities.json"
    scored = tmp_path / "scored.json"
    report = tmp_path / "report.md"
    run_cli("discover", "--source", "fixture", "--out", str(discovered))
    run_cli("score", str(discovered), "--out", str(scored))

    result = run_cli("report", str(scored), "--out", str(report))

    markdown = report.read_text(encoding="utf-8")
    assert result.stdout == ""
    assert result.stderr == ""
    assert "# Bounty Sieve Decision Brief" in markdown
    assert "## Safety Boundary" in markdown
    assert "## Plain-Language Summary" in markdown
    assert "- pursue: 2" in markdown
    assert "- watch: 2" in markdown
    assert "- reject: 3" in markdown
    assert "## Fastest Safe Wins" in markdown
    assert "safe-docs-quickstart" in markdown
    assert "## Risky / High-Reward Items" in markdown
    assert "## Per-Item Manual Verification Checklist" in markdown
    assert "## Clear Reject/Watch Reasons" in markdown
    assert "prompt or private instruction exfiltration" in markdown
    assert "## Next Actions" in markdown


def test_report_out_dash_writes_markdown_to_stdout_without_dash_file(
    tmp_path: Path,
) -> None:
    discovered = tmp_path / "opportunities.json"
    scored = tmp_path / "scored.json"
    run_cli("discover", "--source", "fixture", "--out", str(discovered))
    run_cli("score", str(discovered), "--out", str(scored))

    result = run_cli("report", str(scored), "--out", "-", cwd=tmp_path)

    assert result.stderr == ""
    assert "# Bounty Sieve Decision Brief" in result.stdout
    assert "## Plain-Language Summary" in result.stdout
    assert "- pursue: 2" in result.stdout
    assert not (tmp_path / "-").exists()


def test_report_invalid_json_fails_without_traceback(tmp_path: Path) -> None:
    scored = tmp_path / "scored.json"
    report = tmp_path / "report.md"
    scored.write_text("{not json", encoding="utf-8")

    result = run_cli_unchecked("report", str(scored), "--out", str(report))

    assert result.returncode == 2
    assert result.stdout == ""
    assert "bounty-sieve report: error: input file is not valid JSON:" in result.stderr
    assert "Traceback" not in result.stderr
    assert not report.exists()


def test_report_summary_prints_concise_stdout_after_writing(tmp_path: Path) -> None:
    discovered = tmp_path / "opportunities.json"
    scored = tmp_path / "scored.json"
    report = tmp_path / "report.md"
    run_cli("discover", "--source", "fixture", "--out", str(discovered))
    run_cli("score", str(discovered), "--out", str(scored))

    result = run_cli("report", str(scored), "--out", str(report), "--summary")

    assert report.exists()
    assert result.stderr == ""
    assert result.stdout == (
        f"Report: {report}\n"
        "Total: 7\n"
        "Recommendations: pursue=2, watch=2, reject=3\n"
        "Summary: Bounty Sieve reviewed 7 opportunities: 2 look worth manual verification, "
        "2 need caution before spending time, and 3 should be rejected under the current safety rules.\n"
    )


def test_report_summary_json_prints_machine_readable_stdout_after_writing(
    tmp_path: Path,
) -> None:
    discovered = tmp_path / "opportunities.json"
    scored = tmp_path / "scored.json"
    report = tmp_path / "report.md"
    run_cli("discover", "--source", "fixture", "--out", str(discovered))
    run_cli("score", str(discovered), "--out", str(scored))

    result = run_cli("report", str(scored), "--out", str(report), "--summary-json")

    assert report.exists()
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "recommendations": {"pursue": 2, "reject": 3, "watch": 2},
        "report_path": str(report),
        "summary": (
            "Bounty Sieve reviewed 7 opportunities: 2 look worth manual verification, "
            "2 need caution before spending time, and 3 should be rejected under the current safety rules."
        ),
        "total": 7,
    }
    assert result.stdout == (
        '{"recommendations": {"pursue": 2, "reject": 3, "watch": 2}, '
        f'"report_path": "{report}", '
        '"summary": "Bounty Sieve reviewed 7 opportunities: 2 look worth manual verification, '
        '2 need caution before spending time, and 3 should be rejected under the current safety rules.", '
        '"total": 7}\n'
    )


def test_report_summary_flags_are_mutually_exclusive(tmp_path: Path) -> None:
    scored = tmp_path / "scored.json"
    report = tmp_path / "report.md"
    scored.write_text("[]", encoding="utf-8")

    result = run_cli_unchecked(
        "report", str(scored), "--out", str(report), "--summary", "--summary-json"
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "not allowed with argument --summary" in result.stderr
    assert not report.exists()


def test_report_out_dash_rejects_summary_to_keep_stdout_report_only(
    tmp_path: Path,
) -> None:
    scored = tmp_path / "scored.json"
    scored.write_text("[]", encoding="utf-8")

    result = run_cli_unchecked(
        "report", str(scored), "--out", "-", "--summary", cwd=tmp_path
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "cannot be used with --out -" in result.stderr
    assert not (tmp_path / "-").exists()


def test_report_out_dash_rejects_summary_json_to_keep_stdout_report_only(
    tmp_path: Path,
) -> None:
    scored = tmp_path / "scored.json"
    scored.write_text("[]", encoding="utf-8")

    result = run_cli_unchecked(
        "report", str(scored), "--out", "-", "--summary-json", cwd=tmp_path
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "cannot be used with --out -" in result.stderr
    assert not (tmp_path / "-").exists()


def test_demo_outputs_all_artifacts(tmp_path: Path) -> None:
    out_dir = tmp_path / "demo"

    result = run_cli("demo", "--out", str(out_dir))

    discovered = out_dir / "discovered.json"
    scored = out_dir / "scored.json"
    report = out_dir / "report.md"
    html_report = out_dir / "report.html"
    assert discovered.exists()
    assert scored.exists()
    assert report.exists()
    assert not html_report.exists()
    assert len(read_json(discovered)) == 7
    assert len(read_json(scored)) == 7
    assert "Bounty Sieve Decision Brief" in report.read_text(encoding="utf-8")
    assert f"Wrote offline demo to {out_dir}" in result.stdout
    assert f"- discovered: {discovered}" in result.stdout
    assert f"- scored: {scored}" in result.stdout
    assert f"- report: {report}" in result.stdout
    assert "Recommendations: pursue=2, watch=2, reject=3" in result.stdout


def test_demo_html_flag_outputs_visual_report_artifact(tmp_path: Path) -> None:
    out_dir = tmp_path / "demo"

    result = run_cli("demo", "--out", str(out_dir), "--html")

    discovered = out_dir / "discovered.json"
    scored = out_dir / "scored.json"
    report = out_dir / "report.md"
    html_report = out_dir / "report.html"
    html = html_report.read_text(encoding="utf-8")
    assert discovered.exists()
    assert scored.exists()
    assert report.exists()
    assert html_report.exists()
    assert "<!doctype html>" in html
    assert "Bounty Sieve Demo Report" in html
    assert "Safety Boundary" in html
    assert "Fastest Safe Wins" in html
    assert "Risky / High-Reward Items" in html
    assert "pursue: 2" in html
    assert "watch: 2" in html
    assert "reject: 3" in html
    assert "safe-docs-quickstart" in html
    assert "reject-unknown-token" in html
    assert f"- html: {html_report}" in result.stdout
    assert "Recommendations: pursue=2, watch=2, reject=3" in result.stdout
