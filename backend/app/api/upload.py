import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import get_db
from app.models.block import Block
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.section import Section
from app.models.segment import Segment
from app.services.document_parser import parse_document
from app.services.segmentation import segment_chapter


router = APIRouter(prefix="/api/books", tags=["books"])
_ALLOWED_FORMATS = {".docx", ".epub"}
_CHUNK_SIZE = 1024 * 1024


class UploadResponse(BaseModel):
    book_id: uuid.UUID
    title: str
    status: str
    chapters: int
    sections: int
    blocks: int
    segments: int
    original_filename: str
    file_format: str


async def _save_upload(file: UploadFile, destination: Path) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    total = 0

    try:
        with destination.open("wb") as output:
            while chunk := await file.read(_CHUNK_SIZE):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds {settings.max_upload_size_mb} MB limit",
                    )
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    return total


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_book(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    source_language: str = Form(default="en"),
    target_language: str = Form(default="ru"),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")

    original_filename = Path(file.filename).name
    suffix = Path(original_filename).suffix.lower()
    if suffix not in _ALLOWED_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only EPUB and DOCX files are supported at this stage",
        )

    stored_filename = f"{uuid.uuid4()}{suffix}"
    destination = Path(settings.upload_dir) / stored_filename
    await _save_upload(file, destination)

    try:
        document = parse_document(destination, suffix)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document could not be parsed: {exc}",
        ) from exc

    book = Book(
        title=(title or document.title or Path(original_filename).stem).strip(),
        source_language=source_language,
        target_language=target_language,
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_format=suffix.lstrip("."),
        status="parsing",
    )
    db.add(book)

    chapter_count = 0
    section_count = 0
    block_count = 0
    segment_count = 0

    try:
        await db.flush()

        for chapter_position, normalized_chapter in enumerate(document.chapters):
            chapter = Chapter(
                book_id=book.id,
                position=chapter_position,
                title=normalized_chapter.title,
                source_text=normalized_chapter.source_text,
            )
            db.add(chapter)
            await db.flush()
            chapter_count += 1

            section_models: dict[int, Section] = {}
            for normalized_section in normalized_chapter.sections:
                parent = (
                    section_models.get(normalized_section.parent_position)
                    if normalized_section.parent_position is not None
                    else None
                )
                section = Section(
                    chapter_id=chapter.id,
                    parent_section_id=parent.id if parent else None,
                    position=normalized_section.position,
                    level=normalized_section.level,
                    title=normalized_section.title,
                    metadata_json=normalized_section.metadata_json,
                )
                db.add(section)
                await db.flush()
                section_models[normalized_section.position] = section
                section_count += 1

            paragraph_blocks: dict[int, Block] = {}
            paragraph_index = 0
            for normalized_block in normalized_chapter.blocks:
                section = (
                    section_models.get(normalized_block.section_position)
                    if normalized_block.section_position is not None
                    else None
                )
                block = Block(
                    chapter_id=chapter.id,
                    section_id=section.id if section else None,
                    position=normalized_block.position,
                    block_type=normalized_block.block_type,
                    source_text=normalized_block.source_text,
                    metadata_json=normalized_block.metadata_json,
                )
                db.add(block)
                await db.flush()
                block_count += 1

                if normalized_block.block_type != "heading" and normalized_block.source_text:
                    paragraph_blocks[paragraph_index] = block
                    paragraph_index += 1

            drafts = segment_chapter(normalized_chapter)
            segment_models: list[Segment] = []
            for draft in drafts:
                paragraph_index_value = draft.metadata_json.get("paragraph_index")
                source_block = (
                    paragraph_blocks.get(paragraph_index_value)
                    if isinstance(paragraph_index_value, int)
                    else None
                )
                segment_models.append(
                    Segment(
                        chapter_id=chapter.id,
                        block_id=source_block.id if source_block else None,
                        position=draft.position,
                        segment_type=draft.segment_type,
                        source_text=draft.source_text,
                        source_hash=draft.source_hash,
                        metadata_json=draft.metadata_json,
                    )
                )

            db.add_all(segment_models)
            segment_count += len(segment_models)

        book.status = "segmented"
        await db.commit()
        await db.refresh(book)
    except Exception:
        await db.rollback()
        destination.unlink(missing_ok=True)
        raise

    return UploadResponse(
        book_id=book.id,
        title=book.title,
        status=book.status,
        chapters=chapter_count,
        sections=section_count,
        blocks=block_count,
        segments=segment_count,
        original_filename=original_filename,
        file_format=book.file_format or suffix.lstrip("."),
    )
