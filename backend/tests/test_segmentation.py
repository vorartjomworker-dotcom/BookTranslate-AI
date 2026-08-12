from app.services.document_parser import NormalizedChapter
from app.services.segmentation import segment_chapter


def test_segmentation_is_deterministic() -> None:
    chapter = NormalizedChapter(title="Chapter", paragraphs=["First sentence. Second sentence."])

    first = segment_chapter(chapter)
    second = segment_chapter(chapter)

    assert len(first) == 1
    assert first[0].source_text == "First sentence. Second sentence."
    assert first[0].source_hash == second[0].source_hash
    assert len(first[0].source_hash) == 64


def test_long_paragraph_is_split_and_positions_are_contiguous() -> None:
    chapter = NormalizedChapter(
        title="Long",
        paragraphs=["Sentence one. Sentence two. Sentence three."],
    )

    segments = segment_chapter(chapter, max_chars=20)

    assert len(segments) >= 2
    assert [segment.position for segment in segments] == list(range(len(segments)))
    assert all(len(segment.source_text) <= 20 for segment in segments)
