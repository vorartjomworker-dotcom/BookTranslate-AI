from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.quality_evaluation import GlossaryPair, score_translation_deterministically


def _benchmark_score(deterministic_score: float, reference_score: float | None) -> float:
    if reference_score is None:
        return round(deterministic_score, 2)
    return round(deterministic_score * 0.70 + reference_score * 0.30, 2)


def run(dataset_path: Path) -> dict:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    cases: list[dict] = []
    positive_scores: list[float] = []

    for case in payload.get("cases", []):
        glossary = [
            GlossaryPair(
                source_term=item["source_term"],
                target_term=item["target_term"],
                case_sensitive=bool(item.get("case_sensitive", False)),
            )
            for item in case.get("glossary", [])
        ]
        result = score_translation_deterministically(
            case.get("source", ""),
            case.get("candidate", ""),
            glossary=glossary,
            reference=case.get("reference"),
        )
        benchmark_score = _benchmark_score(result.score, result.reference_score)
        expected_min = case.get("expected_min")
        expected_max = case.get("expected_max")
        expected_critical = bool(case.get("expect_critical_fail", False))

        if expected_min is not None and benchmark_score < float(expected_min):
            failures.append(f"{case['id']}: score {benchmark_score} < minimum {expected_min}")
        if expected_max is not None and benchmark_score > float(expected_max):
            failures.append(f"{case['id']}: score {benchmark_score} > maximum {expected_max}")
        if result.critical_fail != expected_critical:
            failures.append(
                f"{case['id']}: critical_fail={result.critical_fail} expected {expected_critical}"
            )
        if case.get("kind") == "positive":
            positive_scores.append(benchmark_score)

        cases.append(
            {
                "id": case["id"],
                "kind": case.get("kind", "unspecified"),
                "benchmark_score": benchmark_score,
                "deterministic_score": result.score,
                "reference_score": result.reference_score,
                "critical_fail": result.critical_fail,
                "dimensions": {
                    "completeness": result.completeness_score,
                    "terminology": result.terminology_score,
                    "technical_integrity": result.technical_integrity_score,
                    "source_leakage": result.source_leakage_score,
                    "hallucination": result.hallucination_score,
                    "style": result.style_score,
                },
                "issues": result.issues,
            }
        )

    positive_mean = round(sum(positive_scores) / len(positive_scores), 2) if positive_scores else 0.0
    positive_mean_min = float(payload.get("positive_mean_min", 0.0))
    if positive_mean < positive_mean_min:
        failures.append(f"positive mean {positive_mean} < required {positive_mean_min}")

    return {
        "schema": payload.get("schema", "unknown"),
        "dataset": str(dataset_path),
        "case_count": len(cases),
        "positive_mean": positive_mean,
        "positive_mean_min": positive_mean_min,
        "passed": not failures,
        "failures": failures,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic translation quality regression checks")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).with_name("golden_translation_cases.json"),
    )
    parser.add_argument("--report", type=Path, default=Path("quality-regression.json"))
    args = parser.parse_args()

    report = run(args.dataset)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Quality regression: {'PASS' if report['passed'] else 'FAIL'}")
    print(f"Cases: {report['case_count']}; positive mean: {report['positive_mean']}")
    for case in report["cases"]:
        print(
            f"- {case['id']}: {case['benchmark_score']} "
            f"(det={case['deterministic_score']}, ref={case['reference_score']}, critical={case['critical_fail']})"
        )
    for failure in report["failures"]:
        print(f"FAIL: {failure}", file=sys.stderr)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
