"""Read-only GitHub issue import helpers."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


GITHUB_API = "https://api.github.com"
GITHUB_ISSUE_RE = re.compile(r"^/([^/]+)/([^/]+)/(?:issues)/([0-9]+)/?$")
SAFE_TIMEOUT_SECONDS = 15


class GitHubImportError(ValueError):
    """Raised when a GitHub issue cannot be imported safely."""


@dataclass(frozen=True)
class GitHubIssueRef:
    owner: str
    repo: str
    number: int

    @property
    def full_repo(self) -> str:
        return f"{self.owner}/{self.repo}"


def import_github_issue_url(url: str) -> dict[str, Any]:
    """Fetch a public GitHub issue and return one normalized opportunity."""
    issue_ref = parse_github_issue_url(url)
    issue = _fetch_json(_api_url(f"/repos/{issue_ref.full_repo}/issues/{issue_ref.number}"))
    comments = _fetch_comments(issue, issue_ref)
    return github_issue_to_opportunity(url, issue_ref, issue, comments)


def import_github_search(
    query: str,
    limit: int = 10,
    include_repo_health: bool = False,
) -> list[dict[str, Any]]:
    """Fetch public GitHub issue search results as normalized opportunities."""
    normalized_query = query.strip()
    if not normalized_query:
        raise GitHubImportError("--source github-search requires --query QUERY")
    if limit < 1 or limit > 50:
        raise GitHubImportError("--limit must be between 1 and 50")

    payload = _fetch_json(_github_search_api_url(normalized_query, limit))
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise GitHubImportError("GitHub search response did not include an items list")

    opportunities: list[dict[str, Any]] = []
    repo_health_cache: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or "pull_request" in item:
            continue
        issue_ref = _issue_ref_from_search_item(item)
        safe_item = {**item, "html_url": _github_issue_html_url(issue_ref)}
        comments = _fetch_comments(item, issue_ref)
        opportunity = github_issue_to_opportunity(
            safe_item["html_url"],
            issue_ref,
            safe_item,
            comments,
        )
        if include_repo_health:
            _enrich_opportunity_with_repo_health(opportunity, issue_ref, repo_health_cache)
        opportunities.append(opportunity)
    return opportunities


def import_url_list(path: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Import supported URLs from a newline-delimited URL file."""
    opportunities: list[dict[str, Any]] = []
    warnings: list[str] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            url = raw_line.strip()
            if not url or url.startswith("#"):
                continue
            if not is_github_issue_url(url):
                warnings.append(f"{path}:{line_number}: skipped unsupported URL: {url}")
                continue
            try:
                opportunities.append(import_github_issue_url(url))
            except GitHubImportError as exc:
                warnings.append(f"{path}:{line_number}: skipped GitHub issue URL: {exc}")
    return opportunities, warnings


def emit_warnings(warnings: list[str]) -> None:
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)


def is_github_issue_url(url: str) -> bool:
    try:
        parse_github_issue_url(url)
    except GitHubImportError:
        return False
    return True


def parse_github_issue_url(url: str) -> GitHubIssueRef:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
        raise GitHubImportError(f"unsupported GitHub issue URL: {url}")
    match = GITHUB_ISSUE_RE.match(parsed.path)
    if not match:
        raise GitHubImportError(f"unsupported GitHub issue URL: {url}")
    owner, repo, number = match.groups()
    return GitHubIssueRef(owner=owner, repo=repo, number=int(number))


def github_issue_to_opportunity(
    url: str,
    issue_ref: GitHubIssueRef,
    issue: dict[str, Any],
    comments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Convert GitHub issue API payloads into the Bounty Sieve opportunity schema."""
    title = _clean_text(str(issue.get("title") or "Untitled GitHub issue"))
    body = str(issue.get("body") or "")
    labels = _label_names(issue.get("labels", []))
    comment_bodies = [str(comment.get("body") or "") for comment in comments]
    evidence = "\n".join([title, body, *labels, *comment_bodies])
    reward = _reward_from_text(evidence)
    signals = _signals_from_issue(issue, labels, body, comment_bodies)

    return {
        "id": _issue_id(issue_ref),
        "title": title,
        "url": str(issue.get("html_url") or url),
        "platform": "github",
        "repo": issue_ref.full_repo,
        "source": "github-issue",
        "labels": labels,
        "summary": _summary_from_body(body, title),
        "reward": reward,
        "signals": signals,
        "metadata": {
            "github": {
                "issue_number": issue_ref.number,
                "state": issue.get("state"),
                "comments_count": _safe_int(issue.get("comments")),
                "created_at": issue.get("created_at"),
                "updated_at": issue.get("updated_at"),
                "closed_at": issue.get("closed_at"),
                "assignee_count": len(issue.get("assignees") or []),
            }
        },
    }


def _fetch_comments(issue: dict[str, Any], issue_ref: GitHubIssueRef) -> list[dict[str, Any]]:
    comment_count = _safe_int(issue.get("comments"))
    if comment_count <= 0:
        return []
    payload = _fetch_json(_comments_api_url(issue_ref))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise GitHubImportError("GitHub comments response was not a list")


def _fetch_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "bounty-sieve/0.3 read-only issue importer",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=SAFE_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise GitHubImportError(f"GitHub fetch failed with HTTP {exc.code}") from exc
    except URLError as exc:
        raise GitHubImportError(f"GitHub fetch failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise GitHubImportError("GitHub fetch timed out") from exc
    except json.JSONDecodeError as exc:
        raise GitHubImportError("GitHub returned invalid JSON") from exc


def _api_url(path: str) -> str:
    return f"{GITHUB_API}{path}"


def _github_search_api_url(query: str, limit: int) -> str:
    return f"{_api_url('/search/issues')}?{urlencode({'q': query, 'per_page': str(limit)})}"


def _comments_api_url(issue_ref: GitHubIssueRef) -> str:
    return _api_url(f"/repos/{issue_ref.full_repo}/issues/{issue_ref.number}/comments")


def _github_issue_html_url(issue_ref: GitHubIssueRef) -> str:
    return f"https://github.com/{issue_ref.full_repo}/issues/{issue_ref.number}"


def _enrich_opportunity_with_repo_health(
    opportunity: dict[str, Any],
    issue_ref: GitHubIssueRef,
    repo_health_cache: dict[str, dict[str, Any]],
) -> None:
    health = _repo_health(issue_ref, repo_health_cache)
    metadata = opportunity.setdefault("metadata", {})
    github_metadata = metadata.setdefault("github", {})
    github_metadata["repo_health"] = dict(health)

    signals = opportunity.setdefault("signals", {})
    signals["repo_activity"] = health["repo_activity"]
    signals["repo_activity_reason"] = health["reason"]
    signals["repo_health_stale"] = health["repo_activity"] == "low"
    signals["repo_archived"] = health.get("archived") is True


def _repo_health(
    issue_ref: GitHubIssueRef,
    repo_health_cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    full_repo = issue_ref.full_repo
    if full_repo not in repo_health_cache:
        try:
            payload = _fetch_json(_api_url(f"/repos/{full_repo}"))
        except GitHubImportError as exc:
            repo_health_cache[full_repo] = _unknown_repo_health(
                f"repo metadata unavailable: {exc}"
            )
        else:
            repo_health_cache[full_repo] = _repo_health_from_payload(payload)
    return repo_health_cache[full_repo]


def _repo_health_from_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return _unknown_repo_health("repo metadata response was not an object")

    archived_value = payload.get("archived")
    archived = archived_value if isinstance(archived_value, bool) else None
    pushed_at = _optional_string_value(payload.get("pushed_at"))
    updated_at = _optional_string_value(payload.get("updated_at"))
    repo_activity, reason = _repo_activity_from_repo_metadata(archived, pushed_at, updated_at)

    return {
        "stars": _safe_optional_int(payload.get("stargazers_count")),
        "open_issues_count": _safe_optional_int(payload.get("open_issues_count")),
        "archived": archived,
        "pushed_at": pushed_at,
        "updated_at": updated_at,
        "repo_activity": repo_activity,
        "reason": reason,
    }


def _unknown_repo_health(reason: str) -> dict[str, Any]:
    return {
        "stars": None,
        "open_issues_count": None,
        "archived": None,
        "pushed_at": None,
        "updated_at": None,
        "repo_activity": "unknown",
        "reason": reason,
    }


def _repo_activity_from_repo_metadata(
    archived: bool | None,
    pushed_at: str | None,
    updated_at: str | None,
) -> tuple[str, str]:
    if archived is True:
        return "low", "repository is archived"

    pushed = _parse_github_timestamp(pushed_at)
    if pushed is not None:
        age_days = (datetime.now(UTC) - pushed).days
        if age_days <= 180:
            return "active", "repository pushed within 180 days"
        return "low", "repository has no push activity within 180 days"

    updated = _parse_github_timestamp(updated_at)
    if updated is not None:
        age_days = (datetime.now(UTC) - updated).days
        if age_days <= 180:
            return "active", "repository updated within 180 days"
        return "low", "repository has no update activity within 180 days"

    return "unknown", "repository activity timestamps unavailable"


def _parse_github_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _optional_string_value(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _safe_optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _issue_ref_from_search_item(item: dict[str, Any]) -> GitHubIssueRef:
    number = item.get("number")
    if not isinstance(number, int) or isinstance(number, bool):
        raise GitHubImportError("GitHub search item was missing an issue number")

    repository_url = item.get("repository_url")
    if isinstance(repository_url, str):
        parsed = urlparse(repository_url)
        expected_prefix = "/repos/"
        if (
            parsed.scheme == "https"
            and parsed.netloc.lower() == "api.github.com"
            and parsed.path.startswith(expected_prefix)
        ):
            parts = parsed.path[len(expected_prefix) :].split("/")
            if len(parts) == 2 and all(parts):
                return GitHubIssueRef(owner=parts[0], repo=parts[1], number=number)

    html_url = item.get("html_url")
    if isinstance(html_url, str):
        return parse_github_issue_url(html_url)

    raise GitHubImportError("GitHub search item was missing repository information")


def _issue_id(issue_ref: GitHubIssueRef) -> str:
    safe_repo = re.sub(r"[^a-z0-9]+", "-", issue_ref.full_repo.lower()).strip("-")
    return f"github-{safe_repo}-{issue_ref.number}"


def _label_names(labels: Any) -> list[str]:
    names: list[str] = []
    if not isinstance(labels, list):
        return names
    for label in labels:
        if isinstance(label, dict):
            name = label.get("name")
        else:
            name = label
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _summary_from_body(body: str, title: str) -> str:
    plain = _clean_text(body)
    if not plain:
        return title
    first_paragraph = plain.split("\n\n", 1)[0].strip()
    return _truncate(first_paragraph, 320)


def _clean_text(text: str) -> str:
    without_html = re.sub(r"<[^>]+>", " ", text)
    without_markdown = re.sub(r"`{1,3}([^`]+)`{1,3}", r"\1", without_html)
    collapsed_lines = [re.sub(r"\s+", " ", line).strip(" -*#\t") for line in without_markdown.splitlines()]
    return "\n".join(line for line in collapsed_lines if line).strip()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _reward_from_text(text: str) -> dict[str, Any]:
    amount = 0
    reward_type = "unknown"
    currency = "USD"
    match = re.search(r"(?:\$|usd\s*)([0-9][0-9,]*(?:\.[0-9]{1,2})?)", text, re.IGNORECASE)
    if not match:
        match = re.search(r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:usd|dollars)", text, re.IGNORECASE)
    if match:
        amount = int(float(match.group(1).replace(",", "")))
        reward_type = "fixed" if _contains_any(text, ["fixed", "paid", "payout", "bounty"]) else "estimated"
    elif _contains_any(text, ["bounty", "reward", "paid"]):
        reward_type = "conditional"
    return {"amount": amount, "currency": currency, "type": reward_type}


def _signals_from_issue(
    issue: dict[str, Any],
    labels: list[str],
    body: str,
    comment_bodies: list[str],
) -> dict[str, Any]:
    text = "\n".join([str(issue.get("title") or ""), body, *labels, *comment_bodies])
    lower = text.lower()
    comments_count = _safe_int(issue.get("comments"))
    unsafe_secret = _contains_any(
        lower,
        [
            "api key",
            "secret",
            "credential",
            "private key",
            "login",
            "password",
            "private repo",
            ".env",
        ],
    )
    prompt_exfiltration = _contains_any(
        lower,
        ["system prompt", "hidden prompt", "private instruction", "jailbreak", "exfiltrat"],
    )
    token_or_asset = _contains_any(
        lower,
        ["connect wallet", "wallet", "airdrop", "unknown token", "token contract", "seed phrase"],
    )
    star_gated = _contains_any(lower, ["star the repo", "star repo", "starring the repo"]) or bool(
        re.search(r"\b(star|starring)\b.{0,40}\b(required|before|proof|eligible|eligibility)\b", lower)
    )
    duplicate_swarm = comments_count >= 8 or _contains_any(
        lower,
        ["duplicate pr", "many prs", "already claimed", "claimed by", "assigned to"],
    )
    complexity = _complexity(lower)
    scope = _scope(lower, unsafe_secret or prompt_exfiltration or token_or_asset, complexity)

    return {
        "requires_secret_access": unsafe_secret,
        "requires_prompt_exfiltration": prompt_exfiltration,
        "requires_token_or_unknown_asset": token_or_asset,
        "star_gated": star_gated,
        "duplicate_pr_swarm": duplicate_swarm,
        "clarity": _clarity(body, lower),
        "repo_activity": _repo_activity(issue),
        "competition": _competition(comments_count, duplicate_swarm, issue),
        "complexity": complexity,
        "tech": _tech(labels, lower),
        "scope": scope,
        "acceptance_criteria": _acceptance_criteria(body),
    }


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _clarity(body: str, lower: str) -> str:
    if _contains_any(lower, ["acceptance criteria", "expected behavior", "steps to reproduce", "definition of done"]):
        return "high"
    if _contains_any(lower, ["fix this", "make better", "asap", "urgent"]) and len(body) < 400:
        return "low"
    if len(_clean_text(body)) >= 160:
        return "medium"
    return "unknown"


def _repo_activity(issue: dict[str, Any]) -> str:
    state = issue.get("state")
    if state == "closed":
        return "low"
    updated_at = issue.get("updated_at")
    if isinstance(updated_at, str):
        try:
            updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        except ValueError:
            return "unknown"
        if (datetime.now(UTC) - updated).days <= 180:
            return "active"
        return "low"
    return "unknown"


def _competition(comments_count: int, duplicate_swarm: bool, issue: dict[str, Any]) -> str:
    if duplicate_swarm or comments_count >= 5 or issue.get("assignees"):
        return "high"
    if comments_count >= 2:
        return "medium"
    return "low"


def _complexity(lower: str) -> str:
    if _contains_any(lower, ["refactor", "migration", "architecture", "scalability", "performance", "full backend"]):
        return "high"
    if _contains_any(lower, ["docs", "documentation", "readme", "typo", "test", "tests", "json", "cli"]):
        return "low"
    if _contains_any(lower, ["bug", "feature", "api", "frontend", "backend"]):
        return "medium"
    return "unknown"


def _scope(lower: str, unsafe: bool, complexity: str) -> str:
    if unsafe:
        return "unsafe"
    if _contains_any(lower, ["typo", "one line", "single file"]):
        return "tiny"
    if complexity == "high" or _contains_any(lower, ["full", "entire", "broadly"]):
        return "large"
    if complexity in {"low", "medium"}:
        return "small"
    return "unknown"


def _tech(labels: list[str], lower: str) -> list[str]:
    candidates = {
        "python": ["python", "pyproject", "pytest"],
        "pytest": ["pytest"],
        "json": ["json"],
        "markdown": ["markdown", "readme", "docs", "documentation"],
        "cli": ["cli", "command line"],
        "documentation": ["documentation", "docs", "readme"],
        "javascript": ["javascript", "node"],
        "typescript": ["typescript", "ts"],
        "react": ["react"],
        "go": ["golang", " go "],
        "rust": ["rust"],
    }
    label_text = " ".join(labels).lower()
    combined = f" {label_text} {lower} "
    found = [
        tech
        for tech, needles in candidates.items()
        if any(needle in combined for needle in needles)
    ]
    return found[:8]


def _acceptance_criteria(body: str) -> list[str]:
    criteria: list[str] = []
    capture = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if re.search(r"acceptance criteria|definition of done|expected behavior", line, re.IGNORECASE):
            capture = True
            continue
        if capture and not line:
            if criteria:
                break
            continue
        bullet = re.match(r"^(?:[-*]|\d+[.)]|\[[ xX]\])\s+(.*)$", line)
        if capture and bullet:
            cleaned = _clean_text(bullet.group(1))
            if cleaned:
                criteria.append(_truncate(cleaned, 160))
        elif capture and criteria:
            break
    return criteria[:5]


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0
