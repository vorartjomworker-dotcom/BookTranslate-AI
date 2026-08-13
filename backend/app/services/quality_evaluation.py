from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.glossary_term import GlossaryTerm
from app.models.segment import Segment
from app.models.translation import Translation
from app.models.translation_memory import TranslationMemoryEntry
from app.models.translation_quality_evaluation import TranslationQualityEvaluation
from app.models.translation_version import TranslationVersion

QUALITY_SCHEMA = "quality-v2"
QUALITY_WEIGHTS = {
    "completeness": 0.25,
    "terminology": 0.20,
    "technical_integrity": 0.25,
    "hallucination": 0.20,
    "source_leakage": 0.05,
    "style": 0.05,
}

_URL_RE = re.compile(r"https?://[^\s)\]}>\"']+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_UNIT_PATTERN = r"(?:KiB|MiB|GiB|kHz|MHz|GHz|KB|MB|GB|ns|us|µs|ms|Hz|°C|%|B|V|A|W|s)"
_NUMBER_RE = re.compile(
    rf"(?<![\w])[-+]?\d+(?:[.,]\d+)?(?:\s?{_UNIT_PATTERN})?(?![\w])",
    re.IGNORECASE,
)
_CODE_RE = re.compile(
    r"`[^`\n]+`|--[A-Za-z0-9][\w-]*|\b(?:std::[A-Za-z_]\w*(?:::\w+)*(?:<[^\s>]+>)?|[A-Za-z_]\w*::[A-Za-z_]\w*|[A-Za-z_]\w*\(\)|[A-Za-z_]\w*\.(?:cpp|cc|c|hpp|hh|h|py|json|ya?ml|toml|ini|md|docx|epub|pdf))\b"
)
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
_LATIN_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'-]{2,}\b")
_SENTENCE_RE = re.compile(r"[.!?…。！？]+")


@dataclass(slots=True, frozen=True)
class GlossaryPair:
    source_term: str
    target_term: str
    case_sensitive: bool = False


@dataclass(slots=True)
class DeterministicQualityResult:
    score: float
    completeness_score: float
    terminology_score: float
    technical_integrity_score: float
    source_leakage_score: float
    hallucination_score: float
    style_score: float
    reference_score: float | None
    critical_fail: bool
    issues: list[dict]
    details: dict


def _round(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _normalize_number(value: str) -> str:
    compact = re.sub(r"\s+", "", value.strip()).casefold()
    return re.sub(r"(?<=\d),(?=\d)", ".", compact)


def _normalize_anchor(value: str) -> str:
    return value.strip().strip("`.,;:!?()[]{}<>").casefold()


def _counter_score(
    source_values: list[str],
    target_values: list[str],
    normalizer,
) -> tuple[float, int, int, list[str], list[str]]:
    source = Counter(normalizer(item) for item in source_values if normalizer(item))
    target = Counter(normalizer(item) for item in target_values if normalizer(item))
    total = sum(source.values())
    matched = sum(min(count, target.get(token, 0)) for token, count in source.items())
    missing: list[str] = []
    extra: list[str] = []
    for token, count in source.items():
        if target.get(token, 0) < count:
            missing.extend([token] * (count - target.get(token, 0)))
    for token, count in target.items():
        if source.get(token, 0) < count:
            extra.extend([token] * (count - source.get(token, 0)))
    score = 100.0 if total == 0 else matched * 100.0 / total
    return _round(score), len(missing), len(extra), missing, extra


def _contains(text: str, needle: str, case_sensitive: bool) -> bool:
    return needle in text if case_sensitive else needle.casefold() in text.casefold()


def _strip_for_numeric_scan(text: str) -> str:
    # URL/e-mail identity is evaluated separately. Removing them here avoids
    # double-counting digits embedded in protocol paths or addresses.
    return _EMAIL_RE.sub(" ", _URL_RE.sub(" ", text))


def _strip_protected_for_language_scan(text: str) -> str:
    # Required preserved anchors are not untranslated prose. Excluding them
    # prevents a retained URL/file/flag from becoming a source-leakage hit.
    value = _URL_RE.sub(" ", text)
    value = _EMAIL_RE.sub(" ", value)
    value = _CODE_RE.sub(" ", value)
    return value


def _terminology_score(
    source: str,
    candidate: str,
    glossary: list[GlossaryPair],
) -> tuple[float, list[dict], int]:
    opportunities = 0
    issues: list[dict] = []
    for item in glossary:
        if not item.source_term.strip() or not _contains(source, item.source_term, item.case_sensitive):
            continue
        opportunities += 1
        if not _contains(candidate, item.target_term, item.case_sensitive):
            issues.append(
                {
                    "kind": "terminology",
                    "severity": "error",
                    "source_term": item.source_term,
                    "expected_target_term": item.target_term,
                }
            )
    if opportunities == 0:
        return 100.0, issues, 0
    return _round((opportunities - len(issues)) * 100.0 / opportunities), issues, opportunities


def _reference_similarity(candidate: str, reference: str | None) -> float | None:
    if not reference:
        return None
    candidate_tokens = [item.casefold() for item in _WORD_RE.findall(candidate)]
    reference_tokens = [item.casefold() for item in _WORD_RE.findall(reference)]
    candidate_counts = Counter(candidate_tokens)
    reference_counts = Counter(reference_tokens)
    overlap = sum(min(count, reference_counts.get(token, 0)) for token, count in candidate_counts.items())
    precision = overlap / max(1, sum(candidate_counts.values()))
    recall = overlap / max(1, sum(reference_counts.values()))
    token_f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    char_ratio = SequenceMatcher(None, " ".join(candidate_tokens), " ".join(reference_tokens)).ratio()
    return _round((token_f1 * 0.65 + char_ratio * 0.35) * 100.0)


def _source_leakage_score(source: str, candidate: str) -> tuple[float, list[str]]:
    source_scan = _strip_protected_for_language_scan(source)
    candidate_scan = _strip_protected_for_language_scan(candidate)
    source_words = [item.casefold() for item in _LATIN_WORD_RE.findall(source_scan)]
    if len(source_words) < 4:
        return 100.0, []
    lowered = " ".join(item.casefold() for item in _LATIN_WORD_RE.findall(candidate_scan))
    hits: list[str] = []
    seen: set[str] = set()
    for index in range(len(source_words) - 3):
        phrase = " ".join(source_words[index : index + 4])
        if phrase in lowered and phrase not in seen:
            seen.add(phrase)
            hits.append(phrase)
    if not hits:
        return 100.0, []
    possible = max(1, len(source_words) - 3)
    penalty = min(100.0, len(hits) * 300.0 / possible)
    return _round(100.0 - penalty), hits[:10]


def _style_score(candidate: str) -> tuple[float, list[dict]]:
    score = 100.0
    issues: list[dict] = []
    if not candidate.strip():
        return 0.0, [{"kind": "empty_translation", "severity": "critical"}]
    if re.search(r" {3,}|\t{2,}", candidate):
        score -= 10
        issues.append({"kind": "excessive_whitespace", "severity": "warning"})
    if re.search(r"([!?.,;:])\1{2,}", candidate):
        score -= 10
        issues.append({"kind": "repeated_punctuation", "severity": "warning"})
    for left, right in [("(", ")"), ("[", "]"), ("{", "}")]:
        if candidate.count(left) != candidate.count(right):
            score -= 12
            issues.append({"kind": "unbalanced_brackets", "severity": "warning", "pair": left + right})
    return _round(score), issues


def score_translation_deterministically(
    source: str,
    candidate: str,
    *,
    glossary: list[GlossaryPair] | None = None,
    reference: str | None = None,
) -> DeterministicQualityResult:
    source = source or ""
    candidate = candidate or ""
    glossary = glossary or []
    issues: list[dict] = []

    source_urls = _URL_RE.findall(source)
    candidate_urls = _URL_RE.findall(candidate)
    url_score, missing_urls, extra_urls, missing_url_values, extra_url_values = _counter_score(
        source_urls, candidate_urls, _normalize_anchor
    )

    source_emails = _EMAIL_RE.findall(source)
    candidate_emails = _EMAIL_RE.findall(candidate)
    email_score, missing_emails, extra_emails, missing_email_values, extra_email_values = _counter_score(
        source_emails, candidate_emails, _normalize_anchor
    )

    source_code = _CODE_RE.findall(source)
    candidate_code = _CODE_RE.findall(candidate)
    code_score, missing_code, extra_code, missing_code_values, extra_code_values = _counter_score(
        source_code, candidate_code, _normalize_anchor
    )

    source_numbers = _NUMBER_RE.findall(_strip_for_numeric_scan(source))
    candidate_numbers = _NUMBER_RE.findall(_strip_for_numeric_scan(candidate))
    numeric_score, missing_numbers, extra_numbers, missing_numeric_values, extra_numeric_values = _counter_score(
        source_numbers, candidate_numbers, _normalize_number
    )

    protected_parts: list[tuple[float, int]] = []
    for score, count in [
        (url_score, len(source_urls)),
        (email_score, len(source_emails)),
        (code_score, len(source_code)),
    ]:
        if count:
            protected_parts.append((score, count))
    protected_score = 100.0
    if protected_parts:
        total_weight = sum(weight for _, weight in protected_parts)
        protected_score = _round(sum(score * weight for score, weight in protected_parts) / total_weight)

    source_tokens = _WORD_RE.findall(source)
    candidate_tokens = _WORD_RE.findall(candidate)
    if not candidate.strip():
        length_score = 0.0
    elif not source_tokens:
        length_score = 100.0
    else:
        ratio = len(candidate_tokens) / max(1, len(source_tokens))
        if ratio < 0.45:
            length_score = _round(ratio / 0.45 * 100.0)
        elif ratio > 2.8:
            length_score = _round(max(0.0, 100.0 - (ratio - 2.8) * 30.0))
        else:
            length_score = 100.0

    source_sentences = max(1, len(_SENTENCE_RE.findall(source)))
    candidate_sentences = max(1, len(_SENTENCE_RE.findall(candidate))) if candidate.strip() else 0
    sentence_ratio = candidate_sentences / source_sentences if source_sentences else 1.0
    sentence_score = 100.0 if sentence_ratio >= 0.5 else _round(sentence_ratio / 0.5 * 100.0)

    completeness_score = _round(
        length_score * 0.25 + sentence_score * 0.15 + numeric_score * 0.30 + protected_score * 0.30
    )
    technical_integrity_score = _round(numeric_score * 0.45 + protected_score * 0.55)

    terminology_score, terminology_issues, terminology_opportunities = _terminology_score(
        source, candidate, glossary
    )
    issues.extend(terminology_issues)

    source_leakage_score, leakage_phrases = _source_leakage_score(source, candidate)
    if leakage_phrases:
        issues.append({"kind": "source_leakage", "severity": "warning", "phrases": leakage_phrases})

    hallucination_penalty = 0.0
    hallucination_penalty += min(70.0, extra_numbers * 20.0)
    hallucination_penalty += min(30.0, (extra_urls + extra_emails) * 15.0)
    hallucination_penalty += min(30.0, extra_code * 10.0)
    if source_tokens and len(candidate_tokens) / max(1, len(source_tokens)) > 2.8:
        hallucination_penalty += 20.0
    hallucination_score = _round(100.0 - min(100.0, hallucination_penalty))

    if missing_numbers:
        issues.append({"kind": "missing_numeric_anchor", "severity": "error", "values": missing_numeric_values[:20]})
    if extra_numbers:
        issues.append({"kind": "extra_numeric_anchor", "severity": "error", "values": extra_numeric_values[:20]})
    if missing_urls:
        issues.append({"kind": "missing_url", "severity": "critical", "values": missing_url_values[:20]})
    if extra_urls:
        issues.append({"kind": "extra_url", "severity": "error", "values": extra_url_values[:20]})
    if missing_emails:
        issues.append({"kind": "missing_email", "severity": "critical", "values": missing_email_values[:20]})
    if extra_emails:
        issues.append({"kind": "extra_email", "severity": "error", "values": extra_email_values[:20]})
    if missing_code:
        issues.append({"kind": "missing_code_anchor", "severity": "error", "values": missing_code_values[:20]})
    if extra_code:
        issues.append({"kind": "extra_code_anchor", "severity": "error", "values": extra_code_values[:20]})

    style_score, style_issues = _style_score(candidate)
    issues.extend(style_issues)

    score = _round(
        completeness_score * QUALITY_WEIGHTS["completeness"]
        + terminology_score * QUALITY_WEIGHTS["terminology"]
        + technical_integrity_score * QUALITY_WEIGHTS["technical_integrity"]
        + hallucination_score * QUALITY_WEIGHTS["hallucination"]
        + source_leakage_score * QUALITY_WEIGHTS["source_leakage"]
        + style_score * QUALITY_WEIGHTS["style"]
    )

    critical_fail = bool(
        not candidate.strip()
        or missing_urls
        or missing_emails
        or (source_numbers and numeric_score < 50.0)
        or ((source_urls or source_emails or source_code) and protected_score < 50.0)
        or hallucination_score < 50.0
    )
    if critical_fail:
        score = min(score, 59.0)

    reference_score = _reference_similarity(candidate, reference)
    details = {
        "schema": QUALITY_SCHEMA,
        "weights": QUALITY_WEIGHTS,
        "anchors": {
            "numeric": {
                "source": len(source_numbers),
                "missing": missing_numbers,
                "extra": extra_numbers,
                "score": numeric_score,
            },
            "url": {"source": len(source_urls), "missing": missing_urls, "extra": extra_urls, "score": url_score},
            "email": {
                "source": len(source_emails),
                "missing": missing_emails,
                "extra": extra_emails,
                "score": email_score,
            },
            "code": {"source": len(source_code), "missing": missing_code, "extra": extra_code, "score": code_score},
            "protected_score": protected_score,
        },
        "length": {
            "source_tokens": len(source_tokens),
            "candidate_tokens": len(candidate_tokens),
            "score": length_score,
        },
        "sentence_score": sentence_score,
        "terminology_opportunities": terminology_opportunities,
        "reference_metric": "token-f1-65+char-sequence-35" if reference else None,
    }
    return DeterministicQualityResult(
        score=score,
        completeness_score=completeness_score,
        terminology_score=terminology_score,
        technical_integrity_score=technical_integrity_score,
        source_leakage_score=source_leakage_score,
        hallucination_score=hallucination_score,
        style_score=style_score,
        reference_score=reference_score,
        critical_fail=critical_fail,
        issues=issues,
        details=details,
    )


def quality_fingerprint(
    source: str,
    candidate: str,
    glossary: list[GlossaryPair],
    reference: str | None,
) -> str:
    payload = {
        "schema": QUALITY_SCHEMA,
        "source": source,
        "candidate": candidate,
        "reference": reference,
        "glossary": [asdict(item) for item in glossary],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def combine_quality_scores(
    deterministic_score: float,
    judge_score: float | None,
    *,
    deterministic_weight: float = 0.45,
    judge_weight: float = 0.55,
    critical_fail: bool = False,
) -> float:
    if judge_score is None:
        combined = deterministic_score
    else:
        deterministic_weight = max(0.0, deterministic_weight)
        judge_weight = max(0.0, judge_weight)
        total = deterministic_weight + judge_weight
        if total <= 0:
            deterministic_weight, judge_weight, total = 1.0, 0.0, 1.0
        combined = (
            deterministic_score * deterministic_weight + judge_score * judge_weight
        ) / total
    combined = _round(combined)
    return min(combined, 59.0) if critical_fail else combined


async def _glossary_for_translation(
    db: AsyncSession,
    translation: Translation,
    segment: Segment,
) -> list[GlossaryPair]:
    chapter = await db.get(Chapter, segment.chapter_id)
    if chapter is None:
        return []
    rows = list(
        (
            await db.execute(
                select(GlossaryTerm).where(
                    GlossaryTerm.book_id == chapter.book_id,
                    GlossaryTerm.target_language == translation.target_language,
                    GlossaryTerm.approved.is_(True),
                    GlossaryTerm.status == "active",
                )
            )
        ).scalars().all()
    )
    return [
        GlossaryPair(item.source_term, item.target_term, item.case_sensitive)
        for item in rows
    ]


async def evaluate_translation_quality_v2(
    db: AsyncSession,
    *,
    version_id: uuid.UUID,
    judge_score: float | None = None,
    deterministic_weight: float = 0.45,
    judge_weight: float = 0.55,
    reference: str | None = None,
    evaluation_mode: str = "runtime",
) -> TranslationQualityEvaluation:
    version = await db.get(TranslationVersion, version_id)
    if version is None:
        raise LookupError("Translation version not found")
    translation = await db.get(Translation, version.translation_id)
    if translation is None:
        raise LookupError("Translation not found")
    segment = await db.get(Segment, translation.segment_id)
    if segment is None:
        raise LookupError("Segment not found")

    glossary = await _glossary_for_translation(db, translation, segment)
    deterministic = score_translation_deterministically(
        segment.source_text or "",
        version.text,
        glossary=glossary,
        reference=reference,
    )
    final_score = combine_quality_scores(
        deterministic.score,
        judge_score,
        deterministic_weight=deterministic_weight,
        judge_weight=judge_weight,
        critical_fail=deterministic.critical_fail,
    )
    fingerprint = quality_fingerprint(
        segment.source_text or "", version.text, glossary, reference
    )
    evaluation = TranslationQualityEvaluation(
        translation_version_id=version.id,
        score_schema=QUALITY_SCHEMA,
        evaluation_mode=evaluation_mode,
        deterministic_score=deterministic.score,
        judge_score=judge_score,
        reference_score=deterministic.reference_score,
        final_score=final_score,
        completeness_score=deterministic.completeness_score,
        terminology_score=deterministic.terminology_score,
        technical_integrity_score=deterministic.technical_integrity_score,
        source_leakage_score=deterministic.source_leakage_score,
        hallucination_score=deterministic.hallucination_score,
        style_score=deterministic.style_score,
        critical_fail=deterministic.critical_fail,
        evaluator_fingerprint=fingerprint,
        issues_json=deterministic.issues,
        details_json={
            **deterministic.details,
            "judge_score": judge_score,
            "score_weights": {
                "deterministic": deterministic_weight,
                "judge": judge_weight,
            },
        },
    )
    db.add(evaluation)
    version.quality_score = final_score
    version.metadata_json = {
        **dict(version.metadata_json or {}),
        "quality_schema": QUALITY_SCHEMA,
        "quality_v2_score": final_score,
        "quality_v2_critical_fail": deterministic.critical_fail,
        "quality_v2_evaluator_fingerprint": fingerprint,
    }

    memory_rows = list(
        (
            await db.execute(
                select(TranslationMemoryEntry).where(
                    TranslationMemoryEntry.origin_translation_version_id == version.id
                )
            )
        ).scalars().all()
    )
    for memory in memory_rows:
        memory.quality_score = final_score
        memory.metadata_json = {
            **dict(memory.metadata_json or {}),
            "quality_schema": QUALITY_SCHEMA,
            "quality_v2_score": final_score,
            "quality_v2_critical_fail": deterministic.critical_fail,
        }
    await db.commit()
    await db.refresh(evaluation)
    return evaluation


async def quality_history(
    db: AsyncSession,
    version_id: uuid.UUID,
) -> list[TranslationQualityEvaluation]:
    return list(
        (
            await db.execute(
                select(TranslationQualityEvaluation)
                .where(TranslationQualityEvaluation.translation_version_id == version_id)
                .order_by(TranslationQualityEvaluation.created_at.desc())
            )
        ).scalars().all()
    )
