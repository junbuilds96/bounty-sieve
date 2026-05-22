# Contributing

Thanks for considering a contribution to Bounty Sieve. This project is intentionally small and read-only while the offline demo is being shaped.

## Development Setup

Use Python 3.11 or newer.

```bash
python -m pip install -e ".[test]"
pytest
```

The CLI can be run from a checkout without publishing or installing globally:

```bash
python -m bounty_sieve --help
python -m bounty_sieve demo --out out/demo
```

## Contribution Guidelines

- Keep discovery read-only unless the project explicitly adds a reviewed connector boundary.
- Do not add code that clones repositories, opens pull requests, contacts maintainers, connects wallets, uses credentials, stars repositories, or attempts prompt/private-data exfiltration.
- Keep the fixture demo deterministic and offline.
- Add or update tests for scoring rules, report rendering, and CLI behavior when changing those areas.
- Do not commit generated demo outputs, caches, local virtual environments, logs, credentials, or editor metadata.

## Pull Request Checklist

- `pytest` passes locally.
- Public behavior is documented in `README.md` when it changes.
- Safety-sensitive behavior is covered by tests.
- New files are suitable for a public MIT-licensed repository.

## Style

Prefer straightforward Python with explicit data structures. The scoring model should remain transparent enough for a reader to audit without external services or hidden state.
