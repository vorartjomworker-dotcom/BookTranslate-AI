from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class NormalizedSection:
    position: int
    level: int
    title: str
    parent_position: int | None = None
    metadata_json: dict = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedBlock:
    position: int
    block_type: str
    source_text: str | None = None
    section_position: int | None = None
    metadata_json: dict = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedChapter:
    title: str | None = None
    paragraphs: list[str] = field(default_factory=list)
    sections: list[NormalizedSection] = field(default_factory=list)
    blocks: list[NormalizedBlock] = field(default_factory=list)

    @property
    def source_text(self) -> str:
        if self.blocks:
            return "\n\n".join(
                block.source_text
                for block in self.blocks
                if block.source_text and block.block_type != "heading"
            )
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
        from app.services.epub_structured_parser import parse_epub

        return parse_epub(path)

    raise ValueError(f"Unsupported document format: {file_format}")
