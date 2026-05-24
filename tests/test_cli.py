from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import bounty_sieve
from bounty_sieve.doctor import run_doctor


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "bounty_sieve", *args],
        check=True,
        text=True,
        capture_output=True,
    )


def run_cli_unchecked(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "bounty_sieve", *args],
        check=False,
        text=True,
        capture_output=True,
    )


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


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
    assert "github-issue" in result.stdout
    assert "url-list" in result.stdout
    assert "read-only public" in result.stdout
    assert "URL fetches" in result.stdout


def test_cli_rejects_invalid_fixture_source(tmp_path: Path) -> None:
    out = tmp_path / "opportunities.json"

    result = run_cli_unchecked("discover", "--source", "network", "--out", str(out))

    assert result.returncode == 2
    assert "invalid choice" in result.stderr
    assert not out.exists()


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


def test_cli_score_missing_input_fails_without_output(tmp_path: Path) -> None:
    out = tmp_path / "scored.json"
    missing = tmp_path / "missing.json"

    result = run_cli_unchecked("score", str(missing), "--out", str(out))

    assert result.returncode != 0
    assert "No such file or directory" in result.stderr
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
    }
    assert set(by_id["safe-docs-quickstart"]) == required_fields


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


def test_demo_outputs_all_artifacts(tmp_path: Path) -> None:
    out_dir = tmp_path / "demo"

    result = run_cli("demo", "--out", str(out_dir))

    discovered = out_dir / "discovered.json"
    scored = out_dir / "scored.json"
    report = out_dir / "report.md"
    assert discovered.exists()
    assert scored.exists()
    assert report.exists()
    assert len(read_json(discovered)) == 7
    assert len(read_json(scored)) == 7
    assert "Bounty Sieve Decision Brief" in report.read_text(encoding="utf-8")
    assert f"Wrote offline demo to {out_dir}" in result.stdout
    assert f"- discovered: {discovered}" in result.stdout
    assert f"- scored: {scored}" in result.stdout
    assert f"- report: {report}" in result.stdout
    assert "Recommendations: pursue=2, watch=2, reject=3" in result.stdout
