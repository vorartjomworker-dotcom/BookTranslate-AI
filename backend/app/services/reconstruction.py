from io import BytesIO
from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument

from app.services.document_parser import NormalizedDocument


def _add_paragraph(document: DocxDocument, text: str, style: str | None = None):
    if style:
        try:
            return document.add_paragraph(text, style=style)
        except KeyError:
            pass
    return document.add_paragraph(text)


def reconstruct_docx(source: NormalizedDocument, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    if source.title:
        document.core_properties.title = source.title

    assets = {asset.position: asset for asset in source.assets}

    for chapter in source.chapters:
        if chapter.title:
            document.add_heading(chapter.title, level=1)

        for block in sorted(chapter.blocks, key=lambda item: item.position):
            text = block.source_text or ""
            if block.block_type == "heading":
                level = int(block.metadata_json.get("level", 2))
                document.add_heading(text, level=max(1, min(level, 9)))
            elif block.block_type == "paragraph":
                _add_paragraph(document, text)
            elif block.block_type == "list_item":
                style = "List Number" if block.metadata_json.get("list_kind") == "number" else "List Bullet"
                _add_paragraph(document, text, style)
            elif block.block_type == "code":
                _add_paragraph(document, text, "No Spacing")
            elif block.block_type == "blockquote":
                _add_paragraph(document, text, "Quote")
            elif block.block_type == "caption":
                _add_paragraph(document, text, "Caption")
            elif block.block_type == "table":
                cells = block.metadata_json.get("cells") or []
                rows_count = len(cells)
                columns_count = max((len(row) for row in cells), default=0)
                if rows_count and columns_count:
                    table = document.add_table(rows=rows_count, cols=columns_count)
                    for row_index, row in enumerate(cells):
                        for column_index, value in enumerate(row):
                            table.cell(row_index, column_index).text = str(value)
            elif block.block_type == "figure":
                asset_position = block.metadata_json.get("asset_position")
                asset = assets.get(asset_position) if isinstance(asset_position, int) else None
                if asset and asset.data:
                    document.add_picture(BytesIO(asset.data))

    document.save(output_path)
    return output_path
