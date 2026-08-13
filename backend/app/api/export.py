import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import get_db
from app.models.book import Book
from app.services.document_export import load_normalized_document
from app.services.reconstruction import reconstruct_docx

router = APIRouter(prefix="/api/books", tags=["export"])
_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/{book_id}/export/docx", response_class=FileResponse)
async def export_book_docx(book_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> FileResponse:
    document = await load_normalized_document(db, book_id, Path(settings.upload_dir))
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    output_path = Path(settings.upload_dir) / "exports" / f"{book_id}.docx"
    reconstruct_docx(document, output_path)
    return FileResponse(output_path, media_type=_DOCX_MEDIA_TYPE, filename=f"{book_id}_reconstructed.docx")


@router.get("/{book_id}/export/translated.docx", response_class=FileResponse)
async def export_translated_book_docx(book_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> FileResponse:
    book = await db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    document = await load_normalized_document(db, book_id, Path(settings.upload_dir), translated=True)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    output_path = Path(settings.upload_dir) / "exports" / f"{book_id}_{book.target_language}.docx"
    reconstruct_docx(document, output_path)
    return FileResponse(
        output_path,
        media_type=_DOCX_MEDIA_TYPE,
        filename=f"{book_id}_{book.target_language}_translated.docx",
    )
