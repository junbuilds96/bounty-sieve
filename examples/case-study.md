# Synthetic Case Study: Agent Bounty Triage

This is a synthetic, fixture-based example. It does not describe real adoption, real payouts, or live GitHub activity.

## Before

A coding agent is handed a mixed list of synthetic bounty-like GitHub issues and public posts, then asked which ones are worth pursuing. The list includes realistic trap patterns:

- a small documentation issue with clear acceptance criteria
- a regression-test issue with a fixed USD reward
- a prompt/context exfiltration request
- a wallet or secret-access request tied to an unknown asset
- a star-gated task that requires proof of repository starring
- a duplicate-PR swarm where many people are submitting nearly identical work
- a vague high-complexity backend task without a benchmark

Without a local triage pass, the agent can waste context inspecting low-value work or cross safety boundaries by following instructions embedded in untrusted issue text.

## Run Bounty Sieve

These commands work in v0.3 and use only bundled synthetic fixtures:

```bash
python -m bounty_sieve discover --source fixture --out out/case-study/discovered.json
python -m bounty_sieve score out/case-study/discovered.json --out out/case-study/scored.json
python -m bounty_sieve report out/case-study/scored.json --out out/case-study/report.md
```

The same workflow can use a user-curated JSON file instead of fixtures:

```bash
python -m bounty_sieve discover --source json --input examples/opportunities.sample.json --out out/discovered.json
python -m bounty_sieve score out/discovered.json --out out/scored.json
python -m bounty_sieve report out/scored.json --out out/report.md
```

## After

The agent stops at local artifacts and reads `out/case-study/report.md` before taking any browser, repository, wallet, credential, or PR action.

Short report excerpt:

```text
Bounty Sieve reviewed 7 opportunities: 2 look worth manual verification, 2 need caution before spending time, and 3 should be rejected under the current safety rules.

- pursue: 2
- watch: 2
- reject: 3

- **Improve CLI quickstart docs for first-time users** (safe-docs-quickstart): $75 estimated reward, ROI 86. First safe check: confirm the public issue is still open, unclaimed, and covered by the stated acceptance criteria.
- **watch** Add one translation string to popular README (watch-duplicate-pr-swarm): $40 estimated reward, ROI capped at 59. Check the risk before investing time: watch: high duplicate PR competition risk; positive: fixed USD reward with credible payment signal; positive: clear issue and acceptance criteria
- **reject despite reward** Recover value from unknown airdrop token contract (reject-unknown-token): $500 estimated reward. Do not pursue unless the unsafe requirement is removed: reject: asks for unknown token or wallet/asset interaction; reject: requires secret, credential, wallet, or private access; watch: vague task boundaries or missing acceptance criteria
- **reject** reject-prompt-exfiltration: reject: requests prompt or private instruction exfiltration; reject: requires secret, credential, wallet, or private access
- **reject** reject-star-gated-bounty: reject: payment or eligibility is gated by repository starring
```

## Value Proof

Bounty Sieve does not decide to work on an issue. It produces a decision brief that separates the next human review step:

- `pursue`: inspect the public issue manually, confirm it is still open and unclaimed, then decide whether to work.
- `watch`: do not spend coding time until the risk is resolved, such as duplicate PR competition or vague acceptance criteria.
- `reject`: do not pursue under the current terms because the opportunity crosses a safety boundary or manipulates engagement.

In this synthetic run, the agent avoids four common traps before spending implementation context:

- Prompt/context exfiltration: rejected because the task asks for private instructions.
- Wallet/secret exposure: rejected because the task asks for wallet or private access to an unknown asset.
- Star-gated reward: rejected because payment or eligibility depends on starring a repository.
- Duplicate-PR swarm: marked watch because the likely outcome is low-value duplicate work.

The useful result is not automation. It is a small, auditable pause between "this looks like a bounty" and "an agent spends context or crosses a boundary."
