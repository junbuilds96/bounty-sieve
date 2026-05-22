# Changelog

All notable changes to this project will be documented in this file.

This project follows a lightweight changelog format inspired by Keep a Changelog and uses semantic versioning for public releases.

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
