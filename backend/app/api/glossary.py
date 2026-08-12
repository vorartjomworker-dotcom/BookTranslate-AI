import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.book import Book
from app.models.glossary_term import GlossaryTerm


router = APIRouter(prefix="/api/books", tags=["glossary"])


class GlossaryCreate(BaseModel):
    source_term: str = Field(min_length=1, max_length=500)
    target_term: str = Field(min_length=1, max_length=500)
    source_language: str = Field(default="en", min_length=2, max_length=20)
    target_language: str = Field(default="ru", min_length=2, max_length=20)
    notes: str | None = None
    case_sensitive: bool = False


class GlossaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_term: str
    target_term: str
    source_language: str
    target_language: str
    notes: str | None
    case_sensitive: bool
    approved: bool
    status: str


@router.post("/{book_id}/glossary", response_model=GlossaryResponse, status_code=status.HTTP_201_CREATED)
async def create_glossary_term(
    book_id: uuid.UUID,
    payload: GlossaryCreate,
    db: AsyncSession = Depends(get_db),
) -> GlossaryTerm:
    if await db.get(Book, book_id) is None:
        raise HTTPException(status_code=404, detail="Book not found")

    existing = await db.execute(
        select(GlossaryTerm).where(
            GlossaryTerm.book_id == book_id,
            GlossaryTerm.source_term == payload.source_term,
            GlossaryTerm.target_language == payload.target_language,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Glossary term already exists")

    term = GlossaryTerm(book_id=book_id, **payload.model_dump())
    db.add(term)
    await db.commit()
    await db.refresh(term)
    return term


@router.get("/{book_id}/glossary", response_model=list[GlossaryResponse])
async def list_glossary_terms(
    book_id: uuid.UUID,
    target_language: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[GlossaryTerm]:
    query = select(GlossaryTerm).where(GlossaryTerm.book_id == book_id)
    if target_language:
        query = query.where(GlossaryTerm.target_language == target_language)
    result = await db.execute(query.order_by(GlossaryTerm.source_term))
    return list(result.scalars().all())
