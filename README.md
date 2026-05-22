# Bounty Sieve

Read-only bounty opportunity triage and safety filtering for open-source work.

`bounty_sieve` is an offline-demo friendly Python package and CLI for triaging
public bounty-like opportunities. The first version intentionally uses a bundled
fixture source only, so it does not need network access or credentials.

## Safety boundary

This MVP is read-only. It does not clone repositories, open pull requests,
connect wallets, use credentials, star repositories, contact maintainers, or
attempt prompt/private-data exfiltration. It produces local JSON and Markdown
artifacts for human review.

## Install for development

```bash
python -m pip install -e ".[test]"
```

The package can also run directly from the repo:

```bash
python -m bounty_sieve --help
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

After installation, the console script is also available:

```bash
bounty-sieve demo --out out/demo
```

The demo writes:

- `discovered.json`: raw fixture opportunities
- `scored.json`: deterministic scoring output
- `report.md`: safety summary, recommendation counts, top opportunities,
  reject/watch reasons, and next actions

## Fixture coverage

The bundled fixture set includes safe small paid tasks and rejects/watch cases:

- Safe documentation quickstart improvement
- Safe regression test task
- Prompt exfiltration request
- Star-gated bounty
- Unknown token or wallet interaction
- Duplicate PR swarm risk
- Vague high-complexity backend task

## Scoring model

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

Recommendations are `pursue`, `watch`, or `reject`. Unsafe or manipulative
requests are rejected even if the advertised reward is high.

## Tests

```bash
pytest
```
