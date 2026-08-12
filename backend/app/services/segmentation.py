import hashlib
import re
from dataclasses import dataclass, field

from app.services.document_parser import NormalizedChapter


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


@dataclass(slots=True)
class SegmentDraft:
    position: int
    source_text: str
    source_hash: str
    segment_type: str = "paragraph"
    metadata_json: dict = field(default_factory=dict)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split_long_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    sentences = _SENTENCE_BOUNDARY.split(text)
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(sentence) > max_chars:
            if current:
                chunks.append(" ".join(current))
                current = []
                current_length = 0
            chunks.extend(sentence[i : i + max_chars] for i in range(0, len(sentence), max_chars))
            continue

        extra = len(sentence) + (1 if current else 0)
        if current and current_length + extra > max_chars:
            chunks.append(" ".join(current))
            current = [sentence]
            current_length = len(sentence)
        else:
            current.append(sentence)
            current_length += extra

    if current:
        chunks.append(" ".join(current))

    return chunks


def segment_chapter(chapter: NormalizedChapter, max_chars: int = 3500) -> list[SegmentDraft]:
    segments: list[SegmentDraft] = []

    for paragraph_index, paragraph in enumerate(chapter.paragraphs):
        normalized = " ".join(paragraph.split()).strip()
        if not normalized:
            continue

        for part_index, part in enumerate(_split_long_text(normalized, max_chars=max_chars)):
            segments.append(
                SegmentDraft(
                    position=len(segments),
                    source_text=part,
                    source_hash=_hash_text(part),
                    metadata_json={
                        "paragraph_index": paragraph_index,
                        "part_index": part_index,
                    },
                )
            )

    return segments
