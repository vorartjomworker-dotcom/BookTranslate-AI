import zipfile
from pathlib import Path

from app.services.docx_parser import parse_docx
from app.services.document_parser import NormalizedBlock, NormalizedChapter, NormalizedDocument
from app.services.epub_export import reconstruct_epub
from app.services.epub_structured_parser import parse_epub
from app.services.reconstruction import reconstruct_docx
from app.services.segmentation import segment_chapter


def _note_document() -> NormalizedDocument:
    return NormalizedDocument(
        title="Notes",
        chapters=[
            NormalizedChapter(
                title="Chapter 1",
                blocks=[
                    NormalizedBlock(
                        position=0,
                        block_type="paragraph",
                        source_text="Body with notes",
                        metadata_json={"footnote_references": ["2"], "endnote_references": ["3"]},
                    ),
                    NormalizedBlock(
                        position=1,
                        block_type="footnote",
                        source_text="Translated footnote body",
                        metadata_json={"note_id": "2", "note_type": "footnote"},
                    ),
                    NormalizedBlock(
                        position=2,
                        block_type="endnote",
                        source_text="Translated endnote body",
                        metadata_json={"note_id": "3", "note_type": "endnote"},
                    ),
                ],
            )
        ],
    )


def test_docx_real_note_parts_round_trip(tmp_path: Path) -> None:
    output = reconstruct_docx(_note_document(), tmp_path / "notes.docx")
    with zipfile.ZipFile(output) as archive:
        assert "word/footnotes.xml" in archive.namelist()
        assert "word/endnotes.xml" in archive.namelist()
        assert b"Translated footnote body" in archive.read("word/footnotes.xml")
        assert b"Translated endnote body" in archive.read("word/endnotes.xml")
        document_xml = archive.read("word/document.xml")
        assert b"footnoteReference" in document_xml
        assert b"endnoteReference" in document_xml

    parsed = parse_docx(output)
    blocks = parsed.chapters[0].blocks
    footnote = next(block for block in blocks if block.block_type == "footnote")
    endnote = next(block for block in blocks if block.block_type == "endnote")
    assert footnote.source_text == "Translated footnote body"
    assert footnote.metadata_json["note_id"] == "2"
    assert endnote.source_text == "Translated endnote body"
    assert endnote.metadata_json["note_id"] == "3"

    drafts = segment_chapter(parsed.chapters[0])
    assert any(item.segment_type == "footnote" and "Translated footnote" in item.source_text for item in drafts)
    assert any(item.segment_type == "endnote" and "Translated endnote" in item.source_text for item in drafts)


def test_epub_semantic_note_round_trip(tmp_path: Path) -> None:
    source = NormalizedDocument(
        title="EPUB Notes",
        chapters=[
            NormalizedChapter(
                title="Chapter",
                blocks=[
                    NormalizedBlock(position=0, block_type="paragraph", source_text="Body"),
                    NormalizedBlock(
                        position=1,
                        block_type="footnote",
                        source_text="Footnote in EPUB",
                        metadata_json={"note_id": "fn-1", "note_type": "footnote"},
                    ),
                ],
            )
        ],
    )
    output = reconstruct_epub(source, tmp_path / "notes.epub", language="ru")
    parsed = parse_epub(output)
    note = next(block for chapter in parsed.chapters for block in chapter.blocks if block.block_type == "footnote")
    assert note.source_text == "Footnote in EPUB"
    assert note.metadata_json["note_id"] == "fn-1"
