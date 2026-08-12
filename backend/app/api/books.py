import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.book import Book


router = APIRouter(prefix="/api/books", tags=["books"])


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    source_language: str = Field(default="en", min_length=2, max_length=20)
    target_language: str = Field(default="ru", min_length=2, max_length=20)
    description: str | None = None


class BookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    source_language: str
    target_language: str
    original_filename: str | None
    file_format: str | None
    status: str
    description: str | None


@router.post("", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
async def create_book(
    payload: BookCreate,
    db: AsyncSession = Depends(get_db),
) -> Book:
    book = Book(
        title=payload.title,
        source_language=payload.source_language,
        target_language=payload.target_language,
        description=payload.description,
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)
    return book


@router.get("", response_model=list[BookResponse])
async def list_books(db: AsyncSession = Depends(get_db)) -> list[Book]:
    result = await db.execute(select(Book).order_by(Book.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{book_id}", response_model=BookResponse)
async def get_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Book:
    book = await db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    return book
