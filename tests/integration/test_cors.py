"""
Tests for CORS configuration on the API Gateway.

Verifies that preflight OPTIONS requests from the UI origin are handled
correctly and that CORS headers are returned on actual API responses.

Requires FIREFLY_UI_URL to be set (e.g., https://firefly-dev.p5software.com).
"""

import requests


def test_cors_preflight_returns_200(api_url, ui_url):
    resp = requests.options(
        f"{api_url}/firmware",
        headers={
            "Origin": ui_url,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type",
        },
        timeout=10,
    )
    assert resp.status_code == 200, (
        f"Preflight OPTIONS returned {resp.status_code}, expected 200. "
        "CORS may not be configured on the API Gateway."
    )


def test_cors_preflight_has_allow_origin(api_url, ui_url):
    resp = requests.options(
        f"{api_url}/firmware",
        headers={
            "Origin": ui_url,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type",
        },
        timeout=10,
    )
    assert "access-control-allow-origin" in resp.headers, (
        "Preflight response missing Access-Control-Allow-Origin header"
    )


def test_cors_preflight_allow_origin_matches_ui(api_url, ui_url):
    resp = requests.options(
        f"{api_url}/firmware",
        headers={
            "Origin": ui_url,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type",
        },
        timeout=10,
    )
    allow_origin = resp.headers.get("access-control-allow-origin", "")
    assert allow_origin == ui_url, (
        f"Access-Control-Allow-Origin is '{allow_origin}', expected '{ui_url}'"
    )


def test_cors_preflight_allows_required_methods(api_url, ui_url):
    resp = requests.options(
        f"{api_url}/firmware",
        headers={
            "Origin": ui_url,
            "Access-Control-Request-Method": "GET",
        },
        timeout=10,
    )
    allow_methods = resp.headers.get("access-control-allow-methods", "")
    for method in ("GET", "POST", "DELETE", "PATCH"):
        assert method in allow_methods.upper(), (
            f"Access-Control-Allow-Methods '{allow_methods}' missing {method}"
        )


def test_cors_get_response_has_allow_origin(api_url, ui_url):
    resp = requests.get(
        f"{api_url}/firmware",
        headers={"Origin": ui_url},
        timeout=10,
    )
    assert "access-control-allow-origin" in resp.headers, (
        "GET response missing Access-Control-Allow-Origin header"
    )
    assert resp.headers["access-control-allow-origin"] == ui_url
