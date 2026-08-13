from app.main import app


def test_stage4_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}
    expected = {
        "/api/books/{book_id}/translation-jobs",
        "/api/chapters/{chapter_id}/translation-jobs",
        "/api/translation-jobs/{job_id}",
        "/api/translation-jobs/{job_id}/cancel",
        "/api/translations/{translation_id}/versions/{version_id}/qa",
        "/api/books/{book_id}/export/translated.docx",
    }
    assert expected.issubset(paths)
