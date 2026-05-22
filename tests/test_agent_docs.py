from __future__ import annotations

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
