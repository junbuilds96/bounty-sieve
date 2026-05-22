# Security Policy

## Supported Versions

The public release line is `0.1.x`. Security fixes are handled on the default branch until a broader release process exists.

## Reporting a Vulnerability

Please report security concerns by opening a private security advisory on GitHub if available, or by contacting the maintainers through the repository's published contact path.

Include:

- A concise description of the issue.
- Steps to reproduce or a minimal proof of concept.
- Impact and affected versions, if known.
- Whether any credentials, private data, wallet interactions, or network actions are involved.

## Safety Boundary

Bounty Sieve's current workflow is offline by default and read-only. Explicit public URL intake only fetches public metadata. It should not clone repositories, open pull requests, connect wallets, use credentials, star repositories, contact maintainers, claim work, log in, comment, or attempt prompt/private-data exfiltration.

Reports that identify a path around that boundary are treated as security-relevant even if no remote exploit is involved.
