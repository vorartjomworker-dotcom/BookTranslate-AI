from app.services.quality_evaluation import (
    GlossaryPair,
    combine_quality_scores,
    score_translation_deterministically,
)


def test_good_technical_translation_scores_high() -> None:
    result = score_translation_deterministically(
        "The hot path must stay below 25 µs and preserve std::atomic semantics.",
        "Горячий путь должен оставаться ниже 25 µs и сохранять семантику std::atomic.",
        glossary=[GlossaryPair("hot path", "горячий путь")],
        reference="Горячий путь должен оставаться ниже 25 µs и сохранять семантику std::atomic.",
    )
    assert result.score >= 95
    assert result.reference_score == 100
    assert result.critical_fail is False
    assert result.terminology_score == 100
    assert result.technical_integrity_score == 100


def test_missing_numeric_and_url_is_critical() -> None:
    result = score_translation_deterministically(
        "Open https://docs.example.test/v1 and use a 30 ms timeout.",
        "Откройте документацию и используйте тайм-аут.",
    )
    assert result.critical_fail is True
    assert result.score <= 59
    kinds = {item["kind"] for item in result.issues}
    assert "missing_url" in kinds
    assert "missing_numeric_anchor" in kinds


def test_extra_numbers_reduce_hallucination_score() -> None:
    result = score_translation_deterministically(
        "The worker reads the queue.",
        "Воркер читает очередь со скоростью 10000 сообщений и использует 8 потоков.",
    )
    assert result.hallucination_score <= 70
    assert any(item["kind"] == "extra_numeric_anchor" for item in result.issues)


def test_glossary_violation_is_measurable() -> None:
    result = score_translation_deterministically(
        "A memory pool reduces allocator jitter.",
        "Куча памяти уменьшает джиттер аллокатора.",
        glossary=[GlossaryPair("memory pool", "пул памяти")],
    )
    assert result.terminology_score == 0
    assert any(item["kind"] == "terminology" for item in result.issues)


def test_critical_fail_caps_combined_llm_score() -> None:
    score = combine_quality_scores(55, 99, deterministic_weight=0.45, judge_weight=0.55, critical_fail=True)
    assert score == 59
