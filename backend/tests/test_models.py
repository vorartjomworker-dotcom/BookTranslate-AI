from sqlalchemy.orm import configure_mappers

from app.models import Block, Book, Chapter, Section, Segment, TranslationQualityEvaluation


def test_document_structure_mappers_configure() -> None:
    configure_mappers()

    assert Book.__tablename__ == "books"
    assert Chapter.__tablename__ == "chapters"
    assert Section.__tablename__ == "sections"
    assert Block.__tablename__ == "blocks"
    assert Segment.__tablename__ == "segments"
    assert TranslationQualityEvaluation.__tablename__ == "translation_quality_evaluations"
