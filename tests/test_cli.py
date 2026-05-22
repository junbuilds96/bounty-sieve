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


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_package_metadata_uses_bounty_sieve_names() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "bounty-sieve"
    assert pyproject["project"]["scripts"] == {
        "bounty-sieve": "bounty_sieve.__main__:main"
    }


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
    assert "## Safety Boundary" in markdown
    assert "- pursue: 2" in markdown
    assert "- watch: 2" in markdown
    assert "- reject: 3" in markdown
    assert "## Top Opportunities" in markdown
    assert "safe-docs-quickstart" in markdown
    assert "## Reject and Watch Reasons" in markdown
    assert "prompt or private instruction exfiltration" in markdown
    assert "## Next Actions" in markdown


def test_demo_outputs_all_artifacts(tmp_path: Path) -> None:
    out_dir = tmp_path / "demo"

    run_cli("demo", "--out", str(out_dir))

    discovered = out_dir / "discovered.json"
    scored = out_dir / "scored.json"
    report = out_dir / "report.md"
    assert discovered.exists()
    assert scored.exists()
    assert report.exists()
    assert len(read_json(discovered)) == 7
    assert len(read_json(scored)) == 7
    assert "Bounty Sieve Report" in report.read_text(encoding="utf-8")
