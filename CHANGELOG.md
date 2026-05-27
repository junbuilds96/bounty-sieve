# Changelog

All notable changes to this project will be documented in this file.

This project follows a lightweight changelog format inspired by Keep a Changelog and uses semantic versioning for public releases.

## [Unreleased]

### Added

- `rank INPUT` command for an offline, read-only ranked terminal view with table and JSON output modes.
- `shortlist INPUT --out PATH` command for exporting a local read-only Markdown or JSON review shortlist after internal scoring and ranking.
- `search-report --query QUERY --out PATH` command for a one-command read-only public GitHub search, scoring, and Markdown decision brief workflow, with optional scored JSON output.

## [0.3.0] - 2026-05-22

### Added

- In-repo Hermes agent skill at `skills/bounty-sieve/SKILL.md` with frontmatter, exact commands, safety gates, untrusted-input rules, and a human approval gate.
- Public GitHub issue intake through `discover --source github-issue --url URL --out PATH`.
- URL-list intake through `discover --source url-list --input urls.txt --out PATH`, with unsupported URLs skipped as warnings.
- `examples/urls.sample.txt` for public URL intake examples.
- Tests for mocked GitHub fetch/parsing, mixed URL lists, agent skill frontmatter, agent documentation, and existing fixture/JSON/demo compatibility.

### Changed

- README and README_CN now include Agent Usage sections explaining how agents load and use the Bounty Sieve skill.
- CLI help now documents the explicit read-only public URL intake sources.
- Version bumped to 0.3.0.

### Security

- Preserved the offline-by-default boundary. Network access is limited to explicit public GitHub issue and URL-list intake commands.
- `GITHUB_TOKEN` is optional only when already set for GitHub rate limiting and is never required or printed.

## [0.2.0] - 2026-05-22

### Added

- User-provided JSON opportunity import through `discover --source json --input PATH --out PATH`.
- Validation errors for malformed JSON imports with field-level messages.
- `examples/opportunities.sample.json` for ordinary users who want to copy and edit public-looking opportunities without coding.
- Decision brief report sections: plain-language summary, fastest safe wins, risky/high-reward items, per-item manual verification checklist, and clear reject/watch reasons.
- Tests for JSON import, invalid input, decision brief sections, sample data, and the existing fixture demo path.

### Changed

- README and README_CN now document the ordinary-user JSON workflow step by step.
- Version bumped to 0.2.0.

## [0.1.0] - 2026-05-22

### Added

- Offline fixture discovery for bounty-like opportunities.
- Deterministic scoring with pursue/watch/reject recommendations.
- Markdown report generation with safety boundary, recommendation counts, top opportunities, reasons, and next actions.
- `bounty-sieve` console script and `python -m bounty_sieve` entrypoint.
- Public release documentation, MIT license, contribution guide, security policy, CI workflow, and expanded test coverage.
