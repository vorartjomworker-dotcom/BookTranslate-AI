from app.main import app


def test_stage9_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/books/{book_id}/figure-render-jobs" in paths
    assert "/api/figure-render-jobs/{job_id}" in paths
    assert "/api/books/{book_id}/figure-renders" in paths
    assert "/api/figure-renders/{render_id}/download-ticket" in paths
    assert "/api/figure-renders/{render_id}/download" in paths
    assert "/api/ops/slo" in paths
