from __future__ import annotations

import html
from pathlib import Path

from ebooklib import epub

from app.services.document_parser import NormalizedBlock, NormalizedDocument


_EPUB_CSS = """
body { font-family: serif; line-height: 1.5; }
pre, code { font-family: monospace; white-space: pre-wrap; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #bbb; padding: 0.35rem; vertical-align: top; }
figure { margin: 1rem 0; }
figcaption, .caption { color: #555; font-size: 0.92em; }
.inline-links { font-size: 0.85em; color: #555; }
.math-source { overflow-x: auto; }
""".strip()


def _inline_suffix(metadata: dict) -> str:
    parts: list[str] = []
    links = metadata.get("hyperlinks") or []
    if links:
        rendered = []
        for link in links:
            href = html.escape(str(link.get("href") or ""), quote=True)
            label = html.escape(str(link.get("text") or href))
            if href:
                rendered.append(f'<a href="{href}">{label}</a>')
        if rendered:
            parts.append('<span class="inline-links">' + " · ".join(rendered) + "</span>")
    for expression in metadata.get("mathml") or []:
        if expression:
            parts.append(f'<span class="math-source">{expression}</span>')
    return (" " + " ".join(parts)) if parts else ""


def _render_block(block: NormalizedBlock, assets: dict[int, tuple[str, str]]) -> str:
    text = html.escape(block.source_text or "")
    metadata = dict(block.metadata_json or {})
    suffix = _inline_suffix(metadata)
    if block.block_type == "heading":
        level = max(2, min(int(metadata.get("level", 2)), 6))
        return f"<h{level}>{text}{suffix}</h{level}>"
    if block.block_type == "paragraph":
        return f"<p>{text}{suffix}</p>"
    if block.block_type == "code":
        return f"<pre><code>{text}</code></pre>"
    if block.block_type == "blockquote":
        return f"<blockquote>{text}{suffix}</blockquote>"
    if block.block_type == "list_item":
        tag = "ol" if metadata.get("list_kind") == "number" else "ul"
        return f"<{tag}><li>{text}{suffix}</li></{tag}>"
    if block.block_type == "caption":
        return f'<p class="caption">{text}{suffix}</p>'
    if block.block_type == "table":
        rows = metadata.get("cells") or []
        body = []
        for row in rows:
            cells = "".join(f"<td>{html.escape(str(value))}</td>" for value in row)
            body.append(f"<tr>{cells}</tr>")
        return "<table><tbody>" + "".join(body) + "</tbody></table>"
    if block.block_type == "figure":
        position = metadata.get("asset_position")
        asset = assets.get(position) if isinstance(position, int) else None
        if not asset:
            return ""
        href, alt_default = asset
        alt = html.escape(str(metadata.get("alt_text") or alt_default or "figure"), quote=True)
        return f'<figure><img src="{html.escape(href, quote=True)}" alt="{alt}" /></figure>'
    return f"<p>{text}{suffix}</p>" if text else ""


def reconstruct_epub(source: NormalizedDocument, output_path: Path, *, language: str = "ru") -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier(output_path.stem)
    book.set_title(source.title or output_path.stem)
    book.set_language(language)

    style = epub.EpubItem(uid="booktranslate-style", file_name="styles/booktranslate.css", media_type="text/css", content=_EPUB_CSS)
    book.add_item(style)

    asset_map: dict[int, tuple[str, str]] = {}
    for asset in source.assets:
        if not asset.data:
            continue
        suffix = Path(asset.original_filename or "asset.bin").suffix or ".bin"
        file_name = f"assets/asset-{asset.position}{suffix}"
        item = epub.EpubItem(
            uid=f"asset-{asset.position}",
            file_name=file_name,
            media_type=asset.media_type or "application/octet-stream",
            content=asset.data,
        )
        book.add_item(item)
        asset_map[asset.position] = (file_name, asset.original_filename or "figure")

    spine = ["nav"]
    toc = []
    for index, chapter in enumerate(source.chapters):
        title = chapter.title or f"Chapter {index + 1}"
        item = epub.EpubHtml(title=title, file_name=f"chapter-{index + 1}.xhtml", lang=language)
        body = [f"<h1>{html.escape(title)}</h1>"]
        body.extend(_render_block(block, asset_map) for block in sorted(chapter.blocks, key=lambda value: value.position))
        item.content = "<html xmlns='http://www.w3.org/1999/xhtml'><head><title>{}</title></head><body>{}</body></html>".format(
            html.escape(title), "".join(body)
        )
        item.add_item(style)
        book.add_item(item)
        spine.append(item)
        toc.append(item)

    book.toc = tuple(toc)
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(output_path), book)
    return output_path
