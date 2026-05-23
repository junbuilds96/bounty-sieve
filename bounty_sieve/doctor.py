"""Local onboarding health checks."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable

from bounty_sieve.fixtures import load_fixture_opportunities
from bounty_sieve.opportunities import load_json_opportunities
from bounty_sieve.reporting import render_report, summarize_report
from bounty_sieve.scoring import score_opportunities


MIN_PYTHON = (3, 11)


def run_doctor(example_path: str | Path | None = None) -> dict[str, Any]:
    """Run offline/local health checks and return an automation-friendly result."""
    minimal_example_path = _default_example_path() if example_path is None else example_path
    checks = [
        _run_check("python_version", _check_python_version),
        _run_check("package_import", _check_package_import),
        _run_check("minimal_example", lambda: _check_minimal_example(minimal_example_path)),
        _run_check("fixture_pipeline", _check_fixture_pipeline),
    ]
    return {"ok": all(check["status"] == "pass" for check in checks), "checks": checks}


def format_doctor_result(result: dict[str, Any]) -> str:
    """Format a doctor result as concise human-readable output."""
    lines = []
    for check in result["checks"]:
        marker = "OK" if check["status"] == "pass" else "FAIL"
        lines.append(f"{marker} {check['name']}: {check['details']['message']}")
    lines.append("Doctor passed" if result["ok"] else "Doctor failed")
    return "\n".join(lines)


def _run_check(name: str, check: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        details = check()
    except Exception as exc:  # pragma: no cover - exact failures are environment-dependent
        details = {"message": str(exc), "error_type": type(exc).__name__}
        return {"name": name, "status": "fail", "details": details}
    return {"name": name, "status": "pass", "details": details}


def _check_python_version() -> dict[str, Any]:
    actual = ".".join(str(part) for part in sys.version_info[:3])
    required = f">={MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
    if sys.version_info < MIN_PYTHON:
        raise RuntimeError(f"Python {required} required, running {actual}")
    return {
        "message": f"Python {actual} satisfies {required}",
        "required": required,
        "actual": actual,
    }


def _check_package_import() -> dict[str, Any]:
    package = importlib.import_module("bounty_sieve")
    version = getattr(package, "__version__", None)
    if not isinstance(version, str) or not version:
        raise RuntimeError("bounty_sieve.__version__ is missing")
    return {"message": f"bounty_sieve {version} importable", "version": version}


def _check_minimal_example(example_path: str | Path) -> dict[str, Any]:
    path = Path(example_path)
    if not path.exists():
        raise RuntimeError(f"example file missing: {path}")
    opportunities = load_json_opportunities(path)
    noun = "opportunity" if len(opportunities) == 1 else "opportunities"
    return {
        "message": f"{len(opportunities)} {noun} validated from {path}",
        "path": str(path),
        "count": len(opportunities),
        "ids": [item["id"] for item in opportunities],
    }


def _check_fixture_pipeline() -> dict[str, Any]:
    opportunities = load_fixture_opportunities()
    scored = score_opportunities(opportunities)
    report = render_report(scored)
    summary = summarize_report(scored)
    if len(scored) != len(opportunities):
        raise RuntimeError("scored opportunity count did not match fixture count")
    if not report.startswith("# Bounty Sieve Decision Brief"):
        raise RuntimeError("report renderer did not produce the expected decision brief")
    counts = {
        "pursue": summary.counts.get("pursue", 0),
        "watch": summary.counts.get("watch", 0),
        "reject": summary.counts.get("reject", 0),
    }
    return {
        "message": (
            f"{len(scored)} fixture opportunities scored and report rendered "
            f"(pursue={counts['pursue']}, watch={counts['watch']}, reject={counts['reject']})"
        ),
        "count": len(scored),
        "recommendations": counts,
    }


def _default_example_path() -> Path:
    return Path(__file__).resolve().parent.parent / "examples" / "minimal-opportunities.json"
