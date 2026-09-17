"""Standalone CLI Test Runner for Judicial Case Summary Application.

Executes all test tiers (Tiers 1-4) and unit suites, records execution metrics,
prints a structured dashboard report, and enforces strict exit code 0 semantics.

Usage:
    python tests/run_all_tests.py
    python tests/run_all_tests.py --tier 1
    python tests/run_all_tests.py --verbose
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class SuiteResult:
    tier_name: str
    target_path: str
    description: str
    total_tests: int
    passed: int
    failed: int
    skipped: int
    duration_seconds: float
    exit_code: int


class MetricCollectorPlugin:
    """Pytest plugin to gather structured execution metrics per suite."""
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            self.total += 1
            if report.passed:
                self.passed += 1
            elif report.failed:
                self.failed += 1
            elif report.skipped:
                self.skipped += 1
        elif report.when == "setup" and report.skipped:
            self.total += 1
            self.skipped += 1


def run_suite(tier_name: str, target_path: Path, description: str, verbose: bool = False) -> SuiteResult:
    """Executes a single test suite file using pytest and returns structured results."""
    collector = MetricCollectorPlugin()
    args = [str(target_path)]
    if verbose:
        args.append("-v")
    else:
        args.append("-q")

    start_time = time.perf_counter()
    ret = pytest.main(args, plugins=[collector])
    duration = time.perf_counter() - start_time

    return SuiteResult(
        tier_name=tier_name,
        target_path=str(target_path.relative_to(PROJECT_ROOT)),
        description=description,
        total_tests=collector.total,
        passed=collector.passed,
        failed=collector.failed,
        skipped=collector.skipped,
        duration_seconds=duration,
        exit_code=int(ret),
    )


def print_dashboard(results: List[SuiteResult], total_elapsed: float) -> None:
    """Prints a modern console dashboard inspired by Google Stitch & Nano Banana visual aesthetics."""
    sep = "=" * 92
    thin_sep = "-" * 92

    print("\n" + sep)
    print(" JUDICIAL CASE SUMMARY - AUTOMATED E2E & UNIT TEST RUNNER")
    print(sep)
    header = f"{'Suite / Tier':<12} | {'Description':<38} | {'Total':<6} | {'Pass':<5} | {'Fail':<5} | {'Time (s)':<8}"
    print(header)
    print(thin_sep)

    total_tests = 0
    total_passed = 0
    total_failed = 0
    total_skipped = 0

    for r in results:
        status_color = ""
        total_tests += r.total_tests
        total_passed += r.passed
        total_failed += r.failed
        total_skipped += r.skipped

        row = (
            f"{r.tier_name:<12} | "
            f"{r.description[:38]:<38} | "
            f"{r.total_tests:<6} | "
            f"{r.passed:<5} | "
            f"{r.failed:<5} | "
            f"{r.duration_seconds:<8.2f}"
        )
        print(row)

    print(thin_sep)
    summary_row = (
        f"{'TOTAL':<12} | "
        f"{'All Test Suites Combined':<38} | "
        f"{total_tests:<6} | "
        f"{total_passed:<5} | "
        f"{total_failed:<5} | "
        f"{total_elapsed:<8.2f}"
    )
    print(summary_row)
    print(sep)

    if total_failed == 0 and total_tests > 0:
        print(" >>> STATUS: [PASS] - ALL TEST TIERS AND WORKLOADS PASSED SUCCESSFULLY (Exit Code 0)")
    else:
        print(f" >>> STATUS: [FAIL] - {total_failed} TEST(S) FAILED")
    print(sep + "\n")


def main():
    parser = argparse.ArgumentParser(description="Judicial Case Summary Test Runner")
    parser.add_argument(
        "--tier",
        type=str,
        default="all",
        choices=["1", "2", "3", "4", "unit", "all"],
        help="Specific tier to execute (1, 2, 3, 4, unit, or all)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose pytest output")
    args = parser.parse_args()

    suite_definitions = [
        {
            "tier_key": "1",
            "tier_name": "Tier 1",
            "path": PROJECT_ROOT / "tests" / "e2e" / "test_e2e_tier1_features.py",
            "description": "F01-F20 Feature Coverage (>=5 tests/feat)",
        },
        {
            "tier_key": "2",
            "tier_name": "Tier 2",
            "path": PROJECT_ROOT / "tests" / "e2e" / "test_e2e_tier2_boundaries.py",
            "description": "Boundary & Edge Cases (ANPP, PAnP, Offline)",
        },
        {
            "tier_key": "3",
            "tier_name": "Tier 3",
            "path": PROJECT_ROOT / "tests" / "e2e" / "test_e2e_tier3_cross_features.py",
            "description": "Cross-Feature Interactions & Pipelines",
        },
        {
            "tier_key": "4",
            "tier_name": "Tier 4",
            "path": PROJECT_ROOT / "tests" / "e2e" / "test_e2e_tier4_workloads.py",
            "description": "Real-World Scenarios S1-S9 on 9 Cases",
        },
    ]

    # Include unit tests if file exists
    unit_path = PROJECT_ROOT / "tests" / "test_pje_indexer.py"
    if unit_path.exists():
        suite_definitions.append({
            "tier_key": "unit",
            "tier_name": "Unit M1",
            "path": unit_path,
            "description": "PJe Indexer & Stamp Parser Unit Suite",
        })

    # Filter suites if specific tier requested
    if args.tier != "all":
        selected = [s for s in suite_definitions if s["tier_key"] == args.tier]
    else:
        selected = suite_definitions

    results: List[SuiteResult] = []
    global_start = time.perf_counter()

    for suite in selected:
        res = run_suite(
            tier_name=suite["tier_name"],
            target_path=suite["path"],
            description=suite["description"],
            verbose=args.verbose,
        )
        results.append(res)

    total_elapsed = time.perf_counter() - global_start
    print_dashboard(results, total_elapsed)

    any_failed = any(r.failed > 0 or r.exit_code != 0 for r in results)
    sys.exit(1 if any_failed else 0)


if __name__ == "__main__":
    main()
