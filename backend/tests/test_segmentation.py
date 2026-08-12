from app.services.document_parser import NormalizedBlock, NormalizedChapter
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


def test_segmentation_preserves_block_type_and_structure_metadata() -> None:
    chapter = NormalizedChapter(
        title="Structured",
        blocks=[
            NormalizedBlock(position=0, block_type="heading", source_text="Section", section_position=0),
            NormalizedBlock(position=1, block_type="paragraph", source_text="Body text.", section_position=0),
            NormalizedBlock(position=2, block_type="code", source_text="int x = 1;", section_position=0),
        ],
    )

    segments = segment_chapter(chapter)

    assert [segment.segment_type for segment in segments] == ["paragraph", "code"]
    assert segments[0].metadata_json["block_position"] == 1
    assert segments[0].metadata_json["section_position"] == 0
    assert segments[1].metadata_json["block_position"] == 2
