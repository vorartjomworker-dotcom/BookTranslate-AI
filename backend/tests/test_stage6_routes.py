from app.main import app


def test_stage6_routes_registered() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/books/{book_id}/workbench" in paths
    assert "/api/translations/{translation_id}/editor-version" in paths
    assert "/api/books/{book_id}/export/translated.epub" in paths
