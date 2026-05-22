# Bounty Sieve

[简体中文](README_CN.md)

Bounty Sieve is a small Python CLI for read-only triage of bounty-like open-source opportunities. The current release is an offline demo: it uses bundled fixtures, applies deterministic scoring rules, and writes local JSON and Markdown artifacts for human review.

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

## Usage

Discover bundled fixture opportunities:

```bash
python -m bounty_sieve discover --source fixture --out out/discovered.json
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

`demo` writes three files under the selected output directory:

- `discovered.json`: raw bundled fixture opportunities
- `scored.json`: deterministic scoring output with recommendation fields
- `report.md`: Markdown report for manual review

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
- Add optional read-only import formats for user-provided JSON.
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
