from app.main import app


def test_stage7_routes_registered() -> None:
    routes = {(route.path, method) for route in app.routes for method in getattr(route, "methods", set())}
    expected = {
        ("/api/auth/bootstrap", "POST"),
        ("/api/auth/me", "GET"),
        ("/api/admin/users", "POST"),
        ("/api/reviews/inbox", "GET"),
        ("/api/human-reviews/{review_id}/assign", "POST"),
        ("/api/human-reviews/{review_id}/comments", "POST"),
        ("/api/translations/{translation_id}/versions/diff", "GET"),
    }
    assert expected <= routes
