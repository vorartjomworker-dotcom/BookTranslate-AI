from app.main import app


def test_translation_engine_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}
    expected = {
        "/api/ai/providers",
        "/api/books/{book_id}/glossary",
        "/api/segments/{segment_id}/translations",
        "/api/segments/{segment_id}/translation-context",
        "/api/segments/{segment_id}/translate",
        "/api/segments/{segment_id}/translate/pipeline",
        "/api/translations/{translation_id}/versions/{version_id}/finalize",
    }
    assert expected.issubset(paths)
