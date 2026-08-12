from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class NormalizedChapter:
    title: str | None = None
    paragraphs: list[str] = field(default_factory=list)

    @property
    def source_text(self) -> str:
        return "\n\n".join(self.paragraphs)


@dataclass(slots=True)
class NormalizedDocument:
    title: str | None = None
    chapters: list[NormalizedChapter] = field(default_factory=list)


def parse_document(path: Path, file_format: str) -> NormalizedDocument:
    normalized_format = file_format.lower().lstrip(".")

    if normalized_format == "docx":
        from app.services.docx_parser import parse_docx

        return parse_docx(path)

    if normalized_format == "epub":
        from app.services.epub_parser import parse_epub

        return parse_epub(path)

    raise ValueError(f"Unsupported document format: {file_format}")
