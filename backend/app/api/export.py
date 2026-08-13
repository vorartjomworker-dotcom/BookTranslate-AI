import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import DevActor, require_min_role
from app.core.config import settings
from app.core.security import create_download_ticket
from app.db import get_db
from app.models.app_user import AppUser
from app.models.book import Book
from app.services.document_export import load_normalized_document
from app.services.epub_export import reconstruct_epub
from app.services.reconstruction import reconstruct_docx
from app.storage.factory import create_storage

router = APIRouter(prefix="/api/books", tags=["export"])
_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_EPUB_MEDIA_TYPE = "application/epub+zip"


class ExportTicketRequest(BaseModel):
    format: str


def _export_path(book_id: uuid.UUID, format_name: str) -> str:
    mapping = {
        "docx": f"/api/books/{book_id}/export/docx",
        "translated.docx": f"/api/books/{book_id}/export/translated.docx",
        "translated.epub": f"/api/books/{book_id}/export/translated.epub",
    }
    path = mapping.get(format_name)
    if path is None:
        raise HTTPException(status_code=422, detail=f"Unsupported export format: {format_name}")
    return path


@router.post("/{book_id}/export-ticket")
async def create_export_ticket(
    book_id: uuid.UUID,
    payload: ExportTicketRequest,
    actor: AppUser | DevActor = Depends(require_min_role("viewer")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if await db.get(Book, book_id) is None:
        raise HTTPException(status_code=404, detail="Book not found")
    path = _export_path(book_id, payload.format)
    if not settings.auth_signing_secret:
        if settings.auth_required:
            raise HTTPException(status_code=503, detail="AUTH_SIGNING_SECRET is required for protected downloads")
        return {"url": path, "expires_in": None}
    token = create_download_ticket(path=path, user_id=str(actor.id) if actor.id else None)
    return {"url": f"{path}?download_token={token}", "expires_in": settings.download_ticket_ttl_seconds}


@router.get("/{book_id}/export/docx", response_class=FileResponse)
async def export_book_docx(book_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> FileResponse:
    storage = create_storage(settings)
    document = await load_normalized_document(db, book_id, Path(settings.upload_dir), storage=storage)
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
    storage = create_storage(settings)
    document = await load_normalized_document(db, book_id, Path(settings.upload_dir), translated=True, storage=storage)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    output_path = Path(settings.upload_dir) / "exports" / f"{book_id}_{book.target_language}.docx"
    reconstruct_docx(document, output_path)
    return FileResponse(output_path, media_type=_DOCX_MEDIA_TYPE, filename=f"{book_id}_{book.target_language}_translated.docx")


@router.get("/{book_id}/export/translated.epub", response_class=FileResponse)
async def export_translated_book_epub(book_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> FileResponse:
    book = await db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    storage = create_storage(settings)
    document = await load_normalized_document(db, book_id, Path(settings.upload_dir), translated=True, storage=storage)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    output_path = Path(settings.upload_dir) / "exports" / f"{book_id}_{book.target_language}.epub"
    reconstruct_epub(document, output_path, language=book.target_language)
    return FileResponse(output_path, media_type=_EPUB_MEDIA_TYPE, filename=f"{book_id}_{book.target_language}_translated.epub")
