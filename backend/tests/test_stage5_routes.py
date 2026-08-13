from app.main import app


def test_stage5_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}
    expected = {
        "/api/ai/model-policies",
        "/api/books/{book_id}/human-reviews",
        "/api/human-reviews/{review_id}/resolve",
        "/api/books/{book_id}/qa-report",
        "/api/books/{book_id}/qa-report/latest",
        "/api/books/{book_id}/terminology-issues",
        "/api/terminology-issues/{issue_id}/status",
    }
    assert expected.issubset(paths)
