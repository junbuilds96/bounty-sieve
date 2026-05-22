from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path


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
    assert pyproject["project"]["license"] == {"file": "LICENSE"}
    assert pyproject["project"]["scripts"] == {
        "bounty-sieve": "bounty_sieve.__main__:main"
    }


def test_cli_help_lists_offline_demo_commands() -> None:
    result = run_cli_unchecked("--help")

    assert result.returncode == 0
    assert "Read-only offline bounty opportunity triage" in result.stdout
    assert "discover" in result.stdout
    assert "score" in result.stdout
    assert "report" in result.stdout
    assert "demo" in result.stdout


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

    run_cli("discover", "--source", "json", "--input", str(source), "--out", str(out))

    opportunities = read_json(out)
    assert opportunities[0]["id"] == "user-docs-fix"
    assert opportunities[0]["source"] == "json"
    assert opportunities[0]["reward"]["currency"] == "USD"
    assert opportunities[0]["signals"]["requires_secret_access"] is False
    assert opportunities[0]["signals"]["acceptance_criteria"] == []


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

    run_cli("report", str(scored), "--out", str(report))

    markdown = report.read_text(encoding="utf-8")
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
