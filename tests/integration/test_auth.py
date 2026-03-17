"""
Tests verifying that authentication is enforced on all protected endpoints
and that the OTA endpoint remains publicly accessible.
"""

import pytest
import requests


# ---------------------------------------------------------------------------
# Protected endpoints — must return 401 without a token
# ---------------------------------------------------------------------------

PROTECTED_ENDPOINTS = [
    ("GET",    "/firmware"),
    ("GET",    "/firmware/00000000-0000-0000-0000-000000000000.zip"),
    ("PATCH",  "/firmware/00000000-0000-0000-0000-000000000000.zip/status"),
    ("DELETE", "/firmware/00000000-0000-0000-0000-000000000000.zip"),
    ("GET",    "/firmware/00000000-0000-0000-0000-000000000000.zip/download"),
    ("GET",    "/users"),
    ("POST",   "/users"),
    ("PATCH",  "/users/nobody@example.com"),
    ("DELETE", "/users/nobody@example.com"),
]


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_protected_endpoint_requires_auth(api_url, method, path):
    """Each protected endpoint must reject unauthenticated requests with 401."""
    resp = requests.request(method, f"{api_url}{path}", timeout=10)
    assert resp.status_code == 401, (
        f"{method} {path} returned {resp.status_code}, expected 401"
    )


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_protected_endpoint_rejects_invalid_token(api_url, method, path):
    """Each protected endpoint must reject a malformed/expired token with 401."""
    headers = {"Authorization": "Bearer this.is.not.a.valid.jwt"}
    resp = requests.request(method, f"{api_url}{path}", headers=headers, timeout=10)
    assert resp.status_code == 401, (
        f"{method} {path} returned {resp.status_code} with invalid token, expected 401"
    )


# ---------------------------------------------------------------------------
# Public endpoint — OTA must remain accessible without authentication
# ---------------------------------------------------------------------------

def test_ota_endpoint_is_public(api_url):
    """GET /ota/{product_id}/{application} must not require authentication."""
    resp = requests.get(
        f"{api_url}/ota/__unknown_product__/__unknown_app__",
        timeout=10,
    )
    # 404 (product not found) or 200 are both valid — what matters is NOT 401
    assert resp.status_code != 401, (
        f"OTA endpoint returned 401 — it must be publicly accessible"
    )


# ---------------------------------------------------------------------------
# Authenticated access — valid token reaches the Lambdas
# ---------------------------------------------------------------------------

def test_firmware_list_accessible_with_valid_token(api_url, auth_headers):
    """GET /firmware returns 200 with a valid token."""
    resp = requests.get(f"{api_url}/firmware", headers=auth_headers, timeout=10)
    assert resp.status_code == 200


def test_firmware_get_item_not_found_with_valid_token(api_url, auth_headers):
    """GET /firmware/{zip_name} returns 404 (not 401) for unknown zip with valid token."""
    resp = requests.get(
        f"{api_url}/firmware/00000000-0000-0000-0000-000000000000.zip",
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 404


def test_users_list_forbidden_without_super(api_url, auth_headers):
    """GET /users returns 200 or 403 with a valid token (never 401)."""
    resp = requests.get(f"{api_url}/users", headers=auth_headers, timeout=10)
    assert resp.status_code in (200, 403), (
        f"GET /users returned {resp.status_code} with valid token"
    )
