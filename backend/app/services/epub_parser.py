from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import ITEM_DOCUMENT, epub

from app.services.document_parser import NormalizedChapter, NormalizedDocument


def _book_title(book: epub.EpubBook, fallback: str) -> str:
    titles = book.get_metadata("DC", "title")
    if titles and titles[0] and titles[0][0]:
        return str(titles[0][0]).strip()
    return fallback


def parse_epub(path: Path) -> NormalizedDocument:
    book = epub.read_epub(str(path))
    title = _book_title(book, path.stem)
    chapters: list[NormalizedChapter] = []

    for item_id, _linear in book.spine:
        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ITEM_DOCUMENT:
            continue

        soup = BeautifulSoup(item.get_content(), "html.parser")
        for unwanted in soup(["script", "style", "nav"]):
            unwanted.decompose()

        heading = soup.find(["h1", "h2", "h3"])
        chapter_title = heading.get_text(" ", strip=True) if heading else None

        paragraphs: list[str] = []
        for element in soup.find_all(["p", "pre", "blockquote", "li"]):
            text = element.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)

        if paragraphs or chapter_title:
            chapters.append(NormalizedChapter(title=chapter_title, paragraphs=paragraphs))

    if not chapters:
        chapters = [NormalizedChapter(title=title, paragraphs=[])]

    return NormalizedDocument(title=title, chapters=chapters)
