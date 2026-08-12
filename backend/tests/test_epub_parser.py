from pathlib import Path

from ebooklib import epub

from app.services.epub_parser import parse_epub


def test_epub_parser_preserves_spine_order(tmp_path: Path) -> None:
    path = tmp_path / "sample.epub"

    book = epub.EpubBook()
    book.set_identifier("sample-id")
    book.set_title("Sample EPUB")
    book.set_language("en")

    first = epub.EpubHtml(title="Chapter One", file_name="chapter_1.xhtml", lang="en")
    first.content = "<html><body><h1>Chapter One</h1><p>First paragraph.</p></body></html>"
    second = epub.EpubHtml(title="Chapter Two", file_name="chapter_2.xhtml", lang="en")
    second.content = "<html><body><h1>Chapter Two</h1><p>Second paragraph.</p></body></html>"

    book.add_item(first)
    book.add_item(second)
    book.toc = (first, second)
    book.spine = [first, second]
    epub.write_epub(str(path), book)

    parsed = parse_epub(path)

    assert parsed.title == "Sample EPUB"
    assert [chapter.title for chapter in parsed.chapters] == ["Chapter One", "Chapter Two"]
    assert parsed.chapters[0].paragraphs == ["First paragraph."]
    assert parsed.chapters[1].paragraphs == ["Second paragraph."]
