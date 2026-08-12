from pathlib import Path

from ebooklib import epub

from app.services.epub_structured_parser import parse_epub


def test_structured_epub_parser_preserves_sections_and_blocks(tmp_path: Path) -> None:
    path = tmp_path / "structured.epub"

    book = epub.EpubBook()
    book.set_identifier("structured-id")
    book.set_title("Structured EPUB")
    book.set_language("en")

    chapter = epub.EpubHtml(title="Chapter One", file_name="chapter_1.xhtml", lang="en")
    chapter.content = (
        "<html><body>"
        "<h1>Chapter One</h1>"
        "<p>Intro paragraph.</p>"
        "<h2>Section A</h2>"
        "<p>Section text.</p>"
        "<h3>Subsection A.1</h3>"
        "<pre>int x = 1;</pre>"
        "</body></html>"
    )

    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.toc = (chapter,)
    book.spine = ["nav", chapter]
    epub.write_epub(str(path), book)

    parsed = parse_epub(path)
    parsed_chapter = parsed.chapters[0]

    assert parsed_chapter.title == "Chapter One"
    assert [(section.level, section.title, section.parent_position) for section in parsed_chapter.sections] == [
        (2, "Section A", None),
        (3, "Subsection A.1", 0),
    ]
    assert [block.block_type for block in parsed_chapter.blocks] == [
        "paragraph",
        "heading",
        "paragraph",
        "heading",
        "code",
    ]
    assert [block.section_position for block in parsed_chapter.blocks] == [None, 0, 0, 1, 1]
