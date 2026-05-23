from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_bounty_sieve_skill_exists_with_hermes_frontmatter() -> None:
    skill = Path("skills/bounty-sieve/SKILL.md")
    text = skill.read_text(encoding="utf-8")

    assert text.startswith("---\n")
    assert "name: bounty-sieve" in text
    assert "description:" in text
    assert "version: 0.3.0" in text
    assert "metadata:" in text
    assert "hermes:" in text
    assert "## Overview" in text
    assert "## When To Use" in text
    assert "## Exact Commands" in text
    assert "## Safety Gates" in text
    assert "## Untrusted External Input Rules" in text
    assert "## Human Approval Gate" in text


def test_readmes_document_agent_workflow() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    readme_cn = Path("README_CN.md").read_text(encoding="utf-8")

    for text in (readme, readme_cn):
        assert "## Agent Usage" in text
        assert "skills/bounty-sieve/SKILL.md" in text
        assert "discover --source github-issue" in text
        assert "discover --source url-list" in text
        assert "GITHUB_TOKEN" in text
        assert "human" in text.lower() or "人类" in text


def test_public_docs_use_numeric_github_issue_examples() -> None:
    docs = [
        Path("README.md"),
        Path("README_CN.md"),
        Path("skills/bounty-sieve/SKILL.md"),
    ]

    for path in docs:
        text = path.read_text(encoding="utf-8")
        invalid_placeholder = "https://github.com/" + "OWNER" + "/REPO/issues/" + "NUMBER"
        invalid_suffix = "/issues/" + "NUMBER"
        assert invalid_placeholder not in text
        assert invalid_suffix not in text
        assert "https://github.com/octocat/Hello-World/issues/1" in text


def test_case_study_is_linked_and_documents_current_commands() -> None:
    case_study = Path("examples/case-study.md")
    case_text = case_study.read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    readme_cn = Path("README_CN.md").read_text(encoding="utf-8")

    assert "examples/case-study.md" in readme
    assert "examples/case-study.md" in readme_cn
    assert "does not describe real adoption" in case_text

    required_commands = [
        "python -m bounty_sieve discover --source fixture --out out/case-study/discovered.json",
        "python -m bounty_sieve score out/case-study/discovered.json --out out/case-study/scored.json",
        "python -m bounty_sieve report out/case-study/scored.json --out out/case-study/report.md",
    ]
    for command in required_commands:
        assert command in case_text

    required_traps = [
        "Prompt/context exfiltration",
        "Wallet/secret exposure",
        "Star-gated reward",
        "Duplicate-PR swarm",
    ]
    for trap in required_traps:
        assert trap in case_text


def test_case_study_offline_command_sequence_still_works(tmp_path: Path) -> None:
    discovered = tmp_path / "discovered.json"
    scored = tmp_path / "scored.json"
    report = tmp_path / "report.md"

    commands = [
        [
            "discover",
            "--source",
            "fixture",
            "--out",
            str(discovered),
        ],
        ["score", str(discovered), "--out", str(scored)],
        ["report", str(scored), "--out", str(report)],
    ]
    for command in commands:
        subprocess.run(
            [sys.executable, "-m", "bounty_sieve", *command],
            check=True,
            text=True,
            capture_output=True,
        )

    text = report.read_text(encoding="utf-8")
    assert "Bounty Sieve reviewed 7 opportunities" in text
    assert "- pursue: 2" in text
    assert "- watch: 2" in text
    assert "- reject: 3" in text
    assert "reject-prompt-exfiltration" in text
    assert "reject-star-gated-bounty" in text
    assert "reject-unknown-token" in text
    assert "watch-duplicate-pr-swarm" in text
