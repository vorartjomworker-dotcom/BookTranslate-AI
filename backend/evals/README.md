# Translation Quality Regression

Stage 11 adds an offline, deterministic quality gate for technical-book translation. It complements the existing multi-model LLM QA evaluator; it does not replace semantic review.

## Quality Score V2

Runtime quality combines two independent layers:

1. **Deterministic evidence (default 45%)** — reproducible checks that do not call an LLM.
2. **LLM judge (default 55%)** — the existing multi-provider six-dimension evaluator for semantic accuracy, terminology, completeness, fluency, technical integrity and style.

If no LLM evaluator is supplied, Quality V2 is deterministic-only. A deterministic critical failure caps the final score at **59/100**, even when an LLM judge returns a higher score.

Deterministic weights are:

| Dimension | Weight |
|---|---:|
| Completeness | 25% |
| Terminology | 20% |
| Technical integrity | 25% |
| Hallucination anchors | 20% |
| Source-language leakage | 5% |
| Mechanical style | 5% |

## Protected technical evidence

The scorer compares source and translation multisets for:

- numbers and supported technical units;
- URLs;
- e-mail addresses;
- CLI flags, inline-code anchors, scoped C++ identifiers and technical filenames.

URLs/e-mail/code anchors are excluded from source-language leakage detection because preserving them is normally correct. Digits embedded inside URLs/e-mail addresses are not double-counted as numeric evidence.

A missing URL/e-mail, severe numeric loss, severe protected-anchor loss, empty translation or severe unsupported-anchor hallucination is a critical failure.

## Terminology

Approved active `GlossaryTerm` rows for the book and target language are checked whenever their source term occurs in a segment. Missing required target terminology lowers the terminology dimension and emits a structured issue.

## Reference score

Golden evaluation cases may provide a trusted reference. The offline reference score is intentionally simple and reproducible: 65% token-F1 plus 35% normalized character-sequence similarity. It is evidence for regression testing, not a semantic equivalence metric.

## Golden/adversarial corpus

`golden_translation_cases.json` contains synthetic technical examples only. Positive cases must retain technical evidence and approved terminology. Adversarial cases intentionally remove numbers/URLs, invent unsupported numeric claims or violate glossary requirements.

Run locally:

```bash
cd backend
python evals/run_quality_regression.py \
  --dataset evals/golden_translation_cases.json \
  --report quality-regression.json
```

The runner exits non-zero when:

- a positive case drops below its minimum score;
- an adversarial case rises above its maximum score;
- a critical-failure expectation changes;
- the mean score of positive cases drops below the dataset threshold.

CI uploads `backend-quality-evidence` containing pytest output plus the machine-readable regression report.

## Runtime API

```text
POST /api/translations/{translation_id}/versions/{version_id}/quality-v2
GET  /api/translations/{translation_id}/versions/{version_id}/quality-v2
```

POST accepts optional LLM evaluators, deterministic/judge weights and an optional trusted reference. Every run is stored in `translation_quality_evaluations` with the score schema, dimension scores, issues, critical-failure flag and evaluator fingerprint. The final score is propagated to `TranslationVersion.quality_score` and related translation-memory entries.

## Boundary

Deterministic hallucination detection is intentionally evidence-based. It can reliably flag unsupported numeric/URL/e-mail/code anchors and extreme expansion, but it cannot prove arbitrary semantic factuality. Semantic hallucinations still require the LLM judge and, for high-risk material, human review.
