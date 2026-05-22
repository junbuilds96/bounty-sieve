# Bounty Sieve

[![CI](https://github.com/junbuilds96/bounty-sieve/actions/workflows/ci.yml/badge.svg)](https://github.com/junbuilds96/bounty-sieve/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

[简体中文 README](README_CN.md)

Bounty Sieve is a small Python CLI for read-only triage of bounty-like open-source opportunities. It lets ordinary users paste public opportunities into a simple JSON file, applies deterministic scoring rules, and writes local JSON and Markdown artifacts for human review.

The project is useful as a transparent baseline for evaluating opportunity quality and safety signals before doing any manual work in a browser.

## Safety Boundary

This release is intentionally read-only and offline. It does not:

- clone repositories or inspect local project code
- open pull requests, issues, comments, or other remote actions
- connect wallets, use credentials, handle secrets, or touch private data
- star repositories or participate in engagement-gated tasks
- contact maintainers or bounty posters
- attempt prompt, policy, credential, or private-instruction exfiltration

Unsafe or manipulative opportunities are rejected even when the advertised reward is high.

## Installation

Use Python 3.11 or newer.

For local development:

```bash
python -m pip install -e ".[test]"
```

Run directly from a checkout:

```bash
python -m bounty_sieve --help
```

After installation, the console script is available:

```bash
bounty-sieve --help
```

## Ordinary-User Workflow

Create a JSON file with opportunities you found manually in a browser. You can start by copying `examples/opportunities.sample.json`, or paste this smaller example into `my-opportunities.json`:

```json
{
  "opportunities": [
    {
      "id": "docs-install-check",
      "title": "Add install verification step to a public CLI README",
      "url": "https://example.org/repos/public-cli/issues/42",
      "platform": "github",
      "repo": "public-tools/public-cli",
      "labels": ["documentation", "good first issue", "bounty"],
      "summary": "The README asks users to install the CLI but does not show a command that confirms the install worked.",
      "reward": {
        "amount": 80,
        "currency": "USD",
        "type": "fixed"
      },
      "signals": {
        "requires_secret_access": false,
        "requires_prompt_exfiltration": false,
        "requires_token_or_unknown_asset": false,
        "star_gated": false,
        "duplicate_pr_swarm": false,
        "clarity": "high",
        "repo_activity": "active",
        "competition": "low",
        "complexity": "low",
        "tech": ["markdown", "cli"],
        "scope": "tiny",
        "acceptance_criteria": [
          "README shows one verification command",
          "Example output is included"
        ]
      }
    }
  ]
}
```

Import the file without any network access:

```bash
python -m bounty_sieve discover --source json --input my-opportunities.json --out out/discovered.json
```

Score it and generate a decision brief:

```bash
python -m bounty_sieve score out/discovered.json --out out/scored.json
python -m bounty_sieve report out/scored.json --out out/report.md
```

Open `out/report.md`. The report is a decision brief with a plain-language summary, fastest safe wins, risky or high-reward items, a manual checklist for every item, and clear watch/reject reasons.

Validation errors point to the field that needs attention, for example `opportunities[0].id is required and must be a non-empty string`.

## Quick Demo

Run the offline demo to generate local review artifacts:

```bash
python -m bounty_sieve demo --out out/demo
```

Sample output:

```text
Wrote offline demo to out/demo
- discovered: out/demo/discovered.json
- scored: out/demo/scored.json
- report: out/demo/report.md
Recommendations: pursue=2, watch=2, reject=3
```

Open `out/demo/report.md` to review the decision brief and safety reasons. The demo uses only bundled fixtures and does not access the network.

## Usage

Discover bundled fixture opportunities:

```bash
python -m bounty_sieve discover --source fixture --out out/discovered.json
```

Import your own JSON opportunities:

```bash
python -m bounty_sieve discover --source json --input my-opportunities.json --out out/discovered.json
```

Score discovered opportunities:

```bash
python -m bounty_sieve score out/discovered.json --out out/scored.json
```

Render a Markdown report:

```bash
python -m bounty_sieve report out/scored.json --out out/report.md
```

Run the full offline demo:

```bash
python -m bounty_sieve demo --out out/demo
```

The same commands are available through the installed script:

```bash
bounty-sieve demo --out out/demo
```

## Output Artifacts

`demo` writes three files under the selected output directory. The JSON workflow writes the same shapes when you choose the paths yourself.

- `discovered.json`: raw bundled fixture opportunities
- `scored.json`: deterministic scoring output with recommendation fields
- `report.md`: Markdown decision brief for manual review

Generated demo output is intentionally ignored by Git.

## Fixture Coverage

The bundled fixture set includes pursue, watch, and reject cases:

- safe documentation quickstart improvement
- safe regression test task
- prompt/private-instruction exfiltration request
- star-gated bounty
- unknown token or wallet interaction
- duplicate PR competition risk
- vague high-complexity backend task

## JSON Input Fields

Each opportunity must include:

- `id`: short unique name, such as `docs-install-check`
- `title`: human-readable title
- `summary`: what the opportunity asks for

Recommended fields:

- `url`, `platform`, `repo`, and `labels`
- `reward.amount`, `reward.currency`, and `reward.type`
- `signals` for safety and triage: secret access, prompt exfiltration, wallet or unknown asset use, star gating, duplicate PR risk, clarity, repo activity, competition, complexity, tech, scope, and acceptance criteria

Missing reward and signal fields default to conservative unknown values. Invalid field types fail with a clear CLI error instead of being silently ignored.

## Scoring Model

Scoring is deterministic and transparent. Each scored opportunity includes:

- `reward_estimate_usd`
- `payment_confidence`
- `issue_clarity`
- `repo_activity`
- `competition_risk`
- `complexity_estimate`
- `tech_match`
- `scope_risk`
- `roi_score`
- `recommendation`
- `reasons`

Recommendations are `pursue`, `watch`, or `reject`. The score is a triage aid, not an instruction to act. A human should still verify payment terms, issue status, maintainer activity, and whether work is already claimed.

## Development

Install the package with test dependencies:

```bash
python -m pip install -e ".[test]"
```

Run tests:

```bash
pytest
```

Run the CLI help:

```bash
python -m bounty_sieve --help
```

Before submitting changes, avoid committing generated files such as `out/`, caches, virtual environments, logs, local environment files, editor metadata, or `.omx/`.

## Roadmap

- Keep the offline demo stable and auditable.
- Add richer fixture coverage for edge cases and safety failures.
- Add more read-only import formats after the JSON workflow stays stable.
- Document any future connector boundary before adding network access.
- Improve report summaries while preserving deterministic output.

## Non-Goals

- Automated bounty claiming or submission.
- Wallet, token, or payment automation.
- Repository starring, engagement farming, or duplicate PR generation.
- Prompt/private-data extraction or credential handling.
- Network discovery in the current offline demo release.
- Replacing human judgment about whether an opportunity is still valid or ethical to pursue.

## License

Bounty Sieve is released under the MIT License. See [LICENSE](LICENSE).
