from app.main import app


def test_quality_v2_routes_are_registered() -> None:
    routes = {(route.path, tuple(sorted(route.methods or []))) for route in app.routes}
    path = "/api/translations/{translation_id}/versions/{version_id}/quality-v2"
    assert (path, ("POST",)) in routes
    assert (path, ("GET",)) in routes
