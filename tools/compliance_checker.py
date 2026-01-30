#!/usr/bin/env python3
"""
Pipe-Works Organization Repository Compliance Checker.

This script audits repositories for compliance with pipe-works organization
standards and policies. It can check a single repository or scan multiple
repositories in a directory.

Standards Checked:
    - Required files (CLAUDE.md, LICENSE, .pre-commit-config.yaml, etc.)
    - Pre-commit hook configuration and versions
    - Pre-commit git hooks installation
    - Python project configuration (pyproject.toml)
    - CI workflow presence
    - License compliance (GPL-3.0)

Usage:
    # Check current directory
    python compliance_checker.py

    # Check a specific repository
    python compliance_checker.py /path/to/repo

    # Check all repos in a directory
    python compliance_checker.py --scan-dir /path/to/workspace

    # Output as JSON
    python compliance_checker.py --format json

    # Fix auto-fixable issues
    python compliance_checker.py --fix

Example:
    $ python compliance_checker.py ~/pipe-works-development/pipeworks_mud_server

    Pipe-Works Compliance Report
    ============================
    Repository: pipeworks_mud_server

    ✓ CLAUDE.md exists
    ✓ LICENSE exists (GPL-3.0)
    ✓ .pre-commit-config.yaml exists
    ✗ Pre-commit hooks not installed (run: pre-commit install)
    ✓ pyproject.toml exists
    ✓ CI workflow exists

    Score: 5/6 (83%)

Author: Pipe-Works Organization
License: GPL-3.0-or-later
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess  # nosec B404 - needed for running fix commands
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

# =============================================================================
# ORGANIZATION STANDARDS CONFIGURATION
# =============================================================================

# Required files that must exist in every repository
REQUIRED_FILES = [
    "CLAUDE.md",
    "LICENSE",
    "README.md",
    ".pre-commit-config.yaml",
    ".gitignore",
]

# Required files for Python projects
PYTHON_PROJECT_FILES = [
    "pyproject.toml",  # Or setup.py for legacy projects
]

# Required CI workflow files
CI_WORKFLOW_FILES = [
    ".github/workflows/ci.yml",
]

# Required pre-commit hooks with minimum versions
# Format: {repo_url: {hook_id: min_version}}
REQUIRED_PRECOMMIT_HOOKS = {
    "https://github.com/pre-commit/pre-commit-hooks": [
        "trailing-whitespace",
        "end-of-file-fixer",
        "check-yaml",
        "check-added-large-files",
    ],
    "https://github.com/psf/black": ["black"],
    "https://github.com/astral-sh/ruff-pre-commit": ["ruff"],
    "https://github.com/pre-commit/mirrors-mypy": ["mypy"],
    "https://github.com/PyCQA/bandit": ["bandit"],
}

# Minimum versions for critical hooks (rev field in pre-commit config)
MIN_HOOK_VERSIONS = {
    "https://github.com/psf/black": "24.0.0",
    "https://github.com/astral-sh/ruff-pre-commit": "v0.1.0",
}

# Expected license identifier
EXPECTED_LICENSE = "GPL-3.0"
LICENSE_PATTERNS = [
    r"GNU GENERAL PUBLIC LICENSE",
    r"Version 3,",  # Match "Version 3," to distinguish from v2
]


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class CheckResult:
    """Result of a single compliance check."""

    name: str
    passed: bool
    message: str
    severity: str = "error"  # error, warning, info
    fix_command: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "severity": self.severity,
            "fix_command": self.fix_command,
        }


@dataclass
class RepoReport:
    """Compliance report for a single repository."""

    repo_path: Path
    repo_name: str
    checks: list[CheckResult] = field(default_factory=list)
    is_python_project: bool = False

    @property
    def passed_count(self) -> int:
        """Count of passed checks."""
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed_count(self) -> int:
        """Count of failed checks."""
        return sum(1 for c in self.checks if not c.passed)

    @property
    def total_count(self) -> int:
        """Total number of checks."""
        return len(self.checks)

    @property
    def score_percent(self) -> float:
        """Compliance score as percentage."""
        if self.total_count == 0:
            return 0.0
        return (self.passed_count / self.total_count) * 100

    @property
    def is_compliant(self) -> bool:
        """True if all error-level checks passed."""
        return all(c.passed for c in self.checks if c.severity == "error")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "repo_path": str(self.repo_path),
            "repo_name": self.repo_name,
            "is_python_project": self.is_python_project,
            "checks": [c.to_dict() for c in self.checks],
            "summary": {
                "passed": self.passed_count,
                "failed": self.failed_count,
                "total": self.total_count,
                "score_percent": round(self.score_percent, 1),
                "is_compliant": self.is_compliant,
            },
        }


# =============================================================================
# COMPLIANCE CHECKS
# =============================================================================


def check_required_files(repo_path: Path) -> list[CheckResult]:
    """Check that all required files exist."""
    results: list[CheckResult] = []

    for filename in REQUIRED_FILES:
        file_path = repo_path / filename
        if file_path.exists():
            results.append(
                CheckResult(
                    name=f"file:{filename}",
                    passed=True,
                    message=f"{filename} exists",
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"file:{filename}",
                    passed=False,
                    message=f"{filename} is missing",
                    severity="error",
                )
            )

    return results


def check_python_project_files(repo_path: Path) -> list[CheckResult]:
    """Check Python project configuration files."""
    results: list[CheckResult] = []

    # Check for pyproject.toml or setup.py
    has_pyproject = (repo_path / "pyproject.toml").exists()
    has_setup_py = (repo_path / "setup.py").exists()

    if has_pyproject:
        results.append(
            CheckResult(
                name="python:pyproject.toml",
                passed=True,
                message="pyproject.toml exists (modern Python project)",
            )
        )
    elif has_setup_py:
        results.append(
            CheckResult(
                name="python:setup.py",
                passed=True,
                message="setup.py exists (legacy Python project)",
                severity="warning",
            )
        )
    else:
        results.append(
            CheckResult(
                name="python:project_config",
                passed=False,
                message="No pyproject.toml or setup.py found",
                severity="error",
            )
        )

    return results


def check_ci_workflows(repo_path: Path) -> list[CheckResult]:
    """Check that required CI workflows exist."""
    results: list[CheckResult] = []

    for workflow_path in CI_WORKFLOW_FILES:
        full_path = repo_path / workflow_path
        if full_path.exists():
            results.append(
                CheckResult(
                    name=f"ci:{workflow_path}",
                    passed=True,
                    message=f"CI workflow {workflow_path} exists",
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"ci:{workflow_path}",
                    passed=False,
                    message=f"CI workflow {workflow_path} is missing",
                    severity="error",
                )
            )

    return results


def check_license(repo_path: Path) -> list[CheckResult]:
    """Check that LICENSE file contains GPL-3.0."""
    results: list[CheckResult] = []
    license_path = repo_path / "LICENSE"

    if not license_path.exists():
        # Already checked in required files
        return results

    try:
        content = license_path.read_text()
        is_gpl3 = all(re.search(pattern, content) for pattern in LICENSE_PATTERNS)

        if is_gpl3:
            results.append(
                CheckResult(
                    name="license:gpl3",
                    passed=True,
                    message="LICENSE is GPL-3.0",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="license:gpl3",
                    passed=False,
                    message="LICENSE does not appear to be GPL-3.0",
                    severity="error",
                )
            )
    except Exception as e:
        results.append(
            CheckResult(
                name="license:readable",
                passed=False,
                message=f"Could not read LICENSE: {e}",
                severity="error",
            )
        )

    return results


def check_precommit_config(repo_path: Path) -> list[CheckResult]:
    """Check pre-commit configuration for required hooks."""
    results: list[CheckResult] = []
    config_path = repo_path / ".pre-commit-config.yaml"

    if not config_path.exists():
        # Already checked in required files
        return results

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)

        if not config or "repos" not in config:
            results.append(
                CheckResult(
                    name="precommit:valid_config",
                    passed=False,
                    message=".pre-commit-config.yaml is empty or invalid",
                    severity="error",
                )
            )
            return results

        # Build a map of configured hooks
        configured_hooks: dict[str, list[str]] = {}
        configured_versions: dict[str, str] = {}

        for repo in config.get("repos", []):
            repo_url = repo.get("repo", "")
            rev = repo.get("rev", "")
            hooks = [h.get("id", "") for h in repo.get("hooks", [])]

            configured_hooks[repo_url] = hooks
            configured_versions[repo_url] = rev

        # Check required hooks
        for repo_url, required_hook_ids in REQUIRED_PRECOMMIT_HOOKS.items():
            if repo_url not in configured_hooks:
                results.append(
                    CheckResult(
                        name=f"precommit:repo:{repo_url.split('/')[-1]}",
                        passed=False,
                        message=f"Missing pre-commit repo: {repo_url}",
                        severity="error",
                    )
                )
                continue

            for hook_id in required_hook_ids:
                if hook_id in configured_hooks[repo_url]:
                    results.append(
                        CheckResult(
                            name=f"precommit:hook:{hook_id}",
                            passed=True,
                            message=f"Hook '{hook_id}' is configured",
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            name=f"precommit:hook:{hook_id}",
                            passed=False,
                            message=f"Hook '{hook_id}' is not configured",
                            severity="error",
                        )
                    )

        # Check minimum versions
        for repo_url, min_version in MIN_HOOK_VERSIONS.items():
            if repo_url in configured_versions:
                current_version = configured_versions[repo_url]
                # Simple version comparison (strip 'v' prefix)
                current_clean = current_version.lstrip("v")
                min_clean = min_version.lstrip("v")

                # This is a simplified comparison - may not work for all version formats
                try:
                    if _compare_versions(current_clean, min_clean) >= 0:
                        results.append(
                            CheckResult(
                                name=f"precommit:version:{repo_url.split('/')[-1]}",
                                passed=True,
                                message=f"Version {current_version} >= {min_version}",
                            )
                        )
                    else:
                        results.append(
                            CheckResult(
                                name=f"precommit:version:{repo_url.split('/')[-1]}",
                                passed=False,
                                message=f"Version {current_version} < {min_version} (update recommended)",
                                severity="warning",
                                fix_command="pre-commit autoupdate",
                            )
                        )
                except ValueError:
                    # Version comparison failed, skip
                    pass

    except yaml.YAMLError as e:
        results.append(
            CheckResult(
                name="precommit:parse",
                passed=False,
                message=f"Failed to parse .pre-commit-config.yaml: {e}",
                severity="error",
            )
        )
    except Exception as e:
        results.append(
            CheckResult(
                name="precommit:read",
                passed=False,
                message=f"Failed to read .pre-commit-config.yaml: {e}",
                severity="error",
            )
        )

    return results


def check_precommit_installed(repo_path: Path) -> list[CheckResult]:
    """Check if pre-commit hooks are installed in git."""
    results: list[CheckResult] = []

    hook_path = repo_path / ".git" / "hooks" / "pre-commit"

    if not (repo_path / ".git").exists():
        results.append(
            CheckResult(
                name="git:repository",
                passed=False,
                message="Not a git repository",
                severity="warning",
            )
        )
        return results

    if hook_path.exists():
        # Check if it's a pre-commit hook (not a custom script)
        try:
            content = hook_path.read_text()
            if "pre-commit" in content:
                results.append(
                    CheckResult(
                        name="precommit:installed",
                        passed=True,
                        message="Pre-commit hooks are installed",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name="precommit:installed",
                        passed=False,
                        message="Git pre-commit hook exists but is not pre-commit",
                        severity="warning",
                    )
                )
        except Exception:
            results.append(
                CheckResult(
                    name="precommit:installed",
                    passed=False,
                    message="Could not read pre-commit hook",
                    severity="warning",
                )
            )
    else:
        results.append(
            CheckResult(
                name="precommit:installed",
                passed=False,
                message="Pre-commit hooks not installed",
                severity="error",
                fix_command="pre-commit install",
            )
        )

    return results


def check_claude_md_content(repo_path: Path) -> list[CheckResult]:
    """Check CLAUDE.md for required sections."""
    results: list[CheckResult] = []
    claude_md_path = repo_path / "CLAUDE.md"

    if not claude_md_path.exists():
        # Already checked in required files
        return results

    try:
        content = claude_md_path.read_text()

        # Check for recommended sections
        recommended_sections = [
            ("Project Overview", r"(?i)#.*project.*overview|#.*overview"),
            ("Common Commands", r"(?i)#.*common.*commands|#.*commands"),
        ]

        for section_name, pattern in recommended_sections:
            if re.search(pattern, content):
                results.append(
                    CheckResult(
                        name=f"claude_md:{section_name.lower().replace(' ', '_')}",
                        passed=True,
                        message=f"CLAUDE.md has '{section_name}' section",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name=f"claude_md:{section_name.lower().replace(' ', '_')}",
                        passed=False,
                        message=f"CLAUDE.md missing '{section_name}' section",
                        severity="warning",
                    )
                )

    except Exception as e:
        results.append(
            CheckResult(
                name="claude_md:readable",
                passed=False,
                message=f"Could not read CLAUDE.md: {e}",
                severity="warning",
            )
        )

    return results


def _compare_versions(v1: str, v2: str) -> int:
    """
    Compare two version strings.

    Returns:
        -1 if v1 < v2
        0 if v1 == v2
        1 if v1 > v2
    """
    # Split by . and compare each part
    parts1 = [int(x) for x in re.split(r"[.\-]", v1) if x.isdigit()]
    parts2 = [int(x) for x in re.split(r"[.\-]", v2) if x.isdigit()]

    # Pad shorter version with zeros
    max_len = max(len(parts1), len(parts2))
    parts1.extend([0] * (max_len - len(parts1)))
    parts2.extend([0] * (max_len - len(parts2)))

    for p1, p2 in zip(parts1, parts2, strict=True):
        if p1 < p2:
            return -1
        if p1 > p2:
            return 1

    return 0


# =============================================================================
# MAIN CHECKER
# =============================================================================


def is_python_project(repo_path: Path) -> bool:
    """Determine if a repository is a Python project."""
    indicators = [
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "Pipfile",
    ]
    return any((repo_path / f).exists() for f in indicators)


def check_repository(repo_path: Path) -> RepoReport:
    """
    Run all compliance checks on a repository.

    Args:
        repo_path: Path to the repository root.

    Returns:
        RepoReport with all check results.
    """
    repo_path = repo_path.resolve()
    report = RepoReport(
        repo_path=repo_path,
        repo_name=repo_path.name,
        is_python_project=is_python_project(repo_path),
    )

    # Run checks
    report.checks.extend(check_required_files(repo_path))
    report.checks.extend(check_license(repo_path))
    report.checks.extend(check_ci_workflows(repo_path))
    report.checks.extend(check_precommit_config(repo_path))
    report.checks.extend(check_precommit_installed(repo_path))
    report.checks.extend(check_claude_md_content(repo_path))

    # Python-specific checks
    if report.is_python_project:
        report.checks.extend(check_python_project_files(repo_path))

    return report


def scan_directory(dir_path: Path) -> list[RepoReport]:
    """
    Scan a directory for repositories and check each one.

    Args:
        dir_path: Path to directory containing repositories.

    Returns:
        List of RepoReports for each repository found.
    """
    reports = []

    for item in sorted(dir_path.iterdir()):
        if item.is_dir() and (item / ".git").exists():
            report = check_repository(item)
            reports.append(report)

    return reports


# =============================================================================
# OUTPUT FORMATTERS
# =============================================================================


def format_text_report(report: RepoReport) -> str:
    """Format a report as human-readable text."""
    lines = [
        "",
        "=" * 60,
        f"Repository: {report.repo_name}",
        f"Path: {report.repo_path}",
        "=" * 60,
        "",
    ]

    # Group checks by category
    categories: dict[str, list[CheckResult]] = {}
    for check in report.checks:
        category = check.name.split(":")[0]
        if category not in categories:
            categories[category] = []
        categories[category].append(check)

    for category, checks in categories.items():
        lines.append(f"[{category.upper()}]")
        for check in checks:
            icon = "✓" if check.passed else "✗"
            severity_marker = ""
            if not check.passed and check.severity == "warning":
                severity_marker = " (warning)"
            lines.append(f"  {icon} {check.message}{severity_marker}")
            if check.fix_command and not check.passed:
                lines.append(f"      Fix: {check.fix_command}")
        lines.append("")

    # Summary
    lines.append("-" * 60)
    lines.append(f"Score: {report.passed_count}/{report.total_count} ({report.score_percent:.0f}%)")
    status = "COMPLIANT" if report.is_compliant else "NON-COMPLIANT"
    lines.append(f"Status: {status}")
    lines.append("")

    return "\n".join(lines)


def format_json_report(reports: list[RepoReport]) -> str:
    """Format reports as JSON."""
    data = {
        "reports": [r.to_dict() for r in reports],
        "summary": {
            "total_repos": len(reports),
            "compliant_repos": sum(1 for r in reports if r.is_compliant),
            "non_compliant_repos": sum(1 for r in reports if not r.is_compliant),
        },
    }
    return json.dumps(data, indent=2)


# =============================================================================
# FIX FUNCTIONS
# =============================================================================


def apply_fixes(repo_path: Path, report: RepoReport) -> list[str]:
    """
    Apply automatic fixes for failed checks.

    Args:
        repo_path: Path to the repository.
        report: The compliance report with check results.

    Returns:
        List of fix commands that were executed.
    """
    executed_fixes = []

    for check in report.checks:
        if not check.passed and check.fix_command:
            print(f"  Applying fix: {check.fix_command}")
            try:
                result = subprocess.run(
                    check.fix_command,
                    shell=True,  # nosec B602 - fix commands are trusted (from our config)
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    executed_fixes.append(check.fix_command)
                    print("    ✓ Success")
                else:
                    print(f"    ✗ Failed: {result.stderr}")
            except Exception as e:
                print(f"    ✗ Error: {e}")

    return executed_fixes


# =============================================================================
# CLI
# =============================================================================


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check repository compliance with pipe-works organization standards.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          Check current directory
  %(prog)s /path/to/repo            Check specific repository
  %(prog)s --scan-dir ~/projects    Check all repos in directory
  %(prog)s --format json            Output as JSON
  %(prog)s --fix                    Apply automatic fixes
        """,
    )

    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to repository or directory to check (default: current directory)",
    )

    parser.add_argument(
        "--scan-dir",
        action="store_true",
        help="Treat path as directory containing multiple repositories",
    )

    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply automatic fixes for failed checks",
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with error code if any repository is non-compliant",
    )

    args = parser.parse_args()

    path = Path(args.path).resolve()

    if not path.exists():
        print(f"Error: Path does not exist: {path}", file=sys.stderr)
        return 1

    # Run checks
    if args.scan_dir:
        reports = scan_directory(path)
        if not reports:
            print(f"No git repositories found in: {path}", file=sys.stderr)
            return 1
    else:
        reports = [check_repository(path)]

    # Apply fixes if requested
    if args.fix:
        print("Applying fixes...")
        for report in reports:
            print(f"\n{report.repo_name}:")
            apply_fixes(report.repo_path, report)
        print("\nRe-running checks...\n")
        # Re-run checks after fixes
        if args.scan_dir:
            reports = scan_directory(path)
        else:
            reports = [check_repository(path)]

    # Output results
    if args.format == "json":
        print(format_json_report(reports))
    else:
        print("\n" + "=" * 60)
        print("PIPE-WORKS ORGANIZATION COMPLIANCE REPORT")
        print("=" * 60)

        for report in reports:
            print(format_text_report(report))

        # Overall summary for multiple repos
        if len(reports) > 1:
            print("=" * 60)
            print("OVERALL SUMMARY")
            print("=" * 60)
            compliant = sum(1 for r in reports if r.is_compliant)
            print(f"Total repositories: {len(reports)}")
            print(f"Compliant: {compliant}")
            print(f"Non-compliant: {len(reports) - compliant}")
            print("")

    # Exit code
    if args.strict:
        return 0 if all(r.is_compliant for r in reports) else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
