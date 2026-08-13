from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from lxml import etree

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_XML_NS = "http://www.w3.org/XML/1998/namespace"
_OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def docx_note_id(value: str | int) -> int:
    try:
        parsed = int(value)
        if parsed > 0:
            return parsed
    except (TypeError, ValueError):
        pass
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return 100000 + int(digest[:7], 16)


def _tag(name: str) -> str:
    return f"{{{_W_NS}}}{name}"


def _append_text_run(paragraph, text: str) -> None:
    parts = text.split("\n")
    for index, part in enumerate(parts):
        if index:
            run = etree.SubElement(paragraph, _tag("r"))
            etree.SubElement(run, _tag("br"))
        if part:
            run = etree.SubElement(paragraph, _tag("r"))
            node = etree.SubElement(run, _tag("t"))
            node.set(f"{{{_XML_NS}}}space", "preserve")
            node.text = part


def _special_note(root, kind: str, note_id: int, note_kind: str) -> None:
    note = etree.SubElement(root, _tag(kind))
    note.set(_tag("id"), str(note_id))
    note.set(_tag("type"), note_kind)
    paragraph = etree.SubElement(note, _tag("p"))
    run = etree.SubElement(paragraph, _tag("r"))
    etree.SubElement(run, _tag("separator" if note_kind == "separator" else "continuationSeparator"))


def _note_xml(kind: str, notes: dict[str, str]) -> bytes:
    plural = f"{kind}s"
    root = etree.Element(_tag(plural), nsmap={"w": _W_NS})
    _special_note(root, kind, -1, "separator")
    _special_note(root, kind, 0, "continuationSeparator")
    reference_tag = "footnoteRef" if kind == "footnote" else "endnoteRef"
    used_ids: set[int] = set()
    for source_id, text in notes.items():
        numeric_id = docx_note_id(source_id)
        while numeric_id in used_ids:
            numeric_id += 1
        used_ids.add(numeric_id)
        note = etree.SubElement(root, _tag(kind))
        note.set(_tag("id"), str(numeric_id))
        paragraph = etree.SubElement(note, _tag("p"))
        reference_run = etree.SubElement(paragraph, _tag("r"))
        etree.SubElement(reference_run, _tag(reference_tag))
        spacer = etree.SubElement(paragraph, _tag("r"))
        spacer_text = etree.SubElement(spacer, _tag("t"))
        spacer_text.set(f"{{{_XML_NS}}}space", "preserve")
        spacer_text.text = " "
        _append_text_run(paragraph, text)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")


def _ensure_override(root, part_name: str, content_type: str) -> None:
    for item in root.findall(f"{{{_CT_NS}}}Override"):
        if item.get("PartName") == part_name:
            item.set("ContentType", content_type)
            return
    node = etree.SubElement(root, f"{{{_CT_NS}}}Override")
    node.set("PartName", part_name)
    node.set("ContentType", content_type)


def _ensure_relationship(root, target: str, relationship_type: str, preferred_id: str) -> None:
    for item in root.findall(f"{{{_REL_NS}}}Relationship"):
        if item.get("Type") == relationship_type:
            item.set("Target", target)
            return
    existing_ids = {item.get("Id") for item in root.findall(f"{{{_REL_NS}}}Relationship")}
    relation_id = preferred_id
    suffix = 1
    while relation_id in existing_ids:
        suffix += 1
        relation_id = f"{preferred_id}{suffix}"
    node = etree.SubElement(root, f"{{{_REL_NS}}}Relationship")
    node.set("Id", relation_id)
    node.set("Type", relationship_type)
    node.set("Target", target)


def inject_note_parts(path: Path, *, footnotes: dict[str, str], endnotes: dict[str, str]) -> None:
    if not footnotes and not endnotes:
        return
    with zipfile.ZipFile(path, "r") as source:
        infos = source.infolist()
        payloads = {info.filename: source.read(info.filename) for info in infos}

    content_types = etree.fromstring(payloads["[Content_Types].xml"])
    relationships = etree.fromstring(payloads["word/_rels/document.xml.rels"])

    replacements: dict[str, bytes] = {}
    if footnotes:
        replacements["word/footnotes.xml"] = _note_xml("footnote", footnotes)
        _ensure_override(
            content_types,
            "/word/footnotes.xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml",
        )
        _ensure_relationship(
            relationships,
            "footnotes.xml",
            f"{_OFFICE_REL}/footnotes",
            "rIdFootnotes",
        )
    if endnotes:
        replacements["word/endnotes.xml"] = _note_xml("endnote", endnotes)
        _ensure_override(
            content_types,
            "/word/endnotes.xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml",
        )
        _ensure_relationship(
            relationships,
            "endnotes.xml",
            f"{_OFFICE_REL}/endnotes",
            "rIdEndnotes",
        )

    replacements["[Content_Types].xml"] = etree.tostring(
        content_types, xml_declaration=True, encoding="UTF-8", standalone="yes"
    )
    replacements["word/_rels/document.xml.rels"] = etree.tostring(
        relationships, xml_declaration=True, encoding="UTF-8", standalone="yes"
    )

    temporary = path.with_name(f".{path.name}.notes.tmp")
    with zipfile.ZipFile(temporary, "w") as target:
        written: set[str] = set()
        for info in infos:
            name = info.filename
            data = replacements.get(name, payloads[name])
            target.writestr(info, data)
            written.add(name)
        for name, data in replacements.items():
            if name not in written:
                target.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
    temporary.replace(path)
