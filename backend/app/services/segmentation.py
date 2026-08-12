import hashlib
import re
from dataclasses import dataclass, field

from app.services.document_parser import NormalizedBlock, NormalizedChapter


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


def _text_sources(chapter: NormalizedChapter) -> list[tuple[str, str, NormalizedBlock | None]]:
    if chapter.blocks:
        return [
            (block.source_text, block.block_type, block)
            for block in chapter.blocks
            if block.source_text and block.block_type != "heading"
        ]

    return [(paragraph, "paragraph", None) for paragraph in chapter.paragraphs]


def segment_chapter(chapter: NormalizedChapter, max_chars: int = 3500) -> list[SegmentDraft]:
    segments: list[SegmentDraft] = []

    for paragraph_index, (text, segment_type, source_block) in enumerate(_text_sources(chapter)):
        normalized = " ".join(text.split()).strip()
        if not normalized:
            continue

        for part_index, part in enumerate(_split_long_text(normalized, max_chars=max_chars)):
            metadata_json = {
                "paragraph_index": paragraph_index,
                "part_index": part_index,
            }
            if source_block is not None:
                metadata_json.update(
                    {
                        "block_position": source_block.position,
                        "section_position": source_block.section_position,
                    }
                )

            segments.append(
                SegmentDraft(
                    position=len(segments),
                    source_text=part,
                    source_hash=_hash_text(part),
                    segment_type=segment_type,
                    metadata_json=metadata_json,
                )
            )

    return segments
