"""
Tests for PATCH /firmware/{zip_name}/status.
"""

import requests


NONEXISTENT = "00000000-0000-0000-0000-000000000000.zip"


# ---------------------------------------------------------------------------
# Error cases (no upload required)
# ---------------------------------------------------------------------------

def test_patch_status_not_found(api_url, auth_headers):
    resp = requests.patch(
        f"{api_url}/firmware/{NONEXISTENT}/status",
        json={"release_status": "TESTING"},
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 404


def test_patch_status_not_found_has_message(api_url, auth_headers):
    resp = requests.patch(
        f"{api_url}/firmware/{NONEXISTENT}/status",
        json={"release_status": "TESTING"},
        headers=auth_headers,
        timeout=10,
    )
    assert "message" in resp.json()


def test_patch_status_missing_release_status_field(api_url, auth_headers, firmware_item):
    resp = requests.patch(
        f"{api_url}/firmware/{firmware_item['zip_name']}/status",
        json={},
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 400


def test_patch_status_missing_body(api_url, auth_headers, firmware_item):
    resp = requests.patch(
        f"{api_url}/firmware/{firmware_item['zip_name']}/status",
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 400


def test_patch_status_invalid_transition_returns_422(api_url, auth_headers, firmware_item):
    # firmware_item is READY_TO_TEST; jumping straight to RELEASED is invalid.
    resp = requests.patch(
        f"{api_url}/firmware/{firmware_item['zip_name']}/status",
        json={"release_status": "RELEASED"},
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 422


def test_patch_status_invalid_transition_response_body(api_url, auth_headers, firmware_item):
    resp = requests.patch(
        f"{api_url}/firmware/{firmware_item['zip_name']}/status",
        json={"release_status": "RELEASED"},
        headers=auth_headers,
        timeout=10,
    )
    body = resp.json()
    assert "message" in body
    assert "current_status" in body
    assert "allowed_transitions" in body
    assert isinstance(body["allowed_transitions"], list)


def test_patch_status_invalid_transition_allowed_transitions_correct(api_url, auth_headers, firmware_item):
    # READY_TO_TEST may only transition to TESTING.
    resp = requests.patch(
        f"{api_url}/firmware/{firmware_item['zip_name']}/status",
        json={"release_status": "RELEASED"},
        headers=auth_headers,
        timeout=10,
    )
    body = resp.json()
    assert body["current_status"] == "READY_TO_TEST"
    assert body["allowed_transitions"] == ["TESTING"]


# ---------------------------------------------------------------------------
# Valid state machine progression (each test needs a fresh item)
# ---------------------------------------------------------------------------

def test_patch_status_ready_to_test_to_testing(api_url, auth_headers, fresh_firmware_item):
    resp = requests.patch(
        f"{api_url}/firmware/{fresh_firmware_item['zip_name']}/status",
        json={"release_status": "TESTING"},
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 200
    assert resp.json()["release_status"] == "TESTING"


def test_patch_status_response_excludes_pk(api_url, auth_headers, fresh_firmware_item):
    resp = requests.patch(
        f"{api_url}/firmware/{fresh_firmware_item['zip_name']}/status",
        json={"release_status": "TESTING"},
        headers=auth_headers,
        timeout=10,
    )
    assert "pk" not in resp.json()


def test_patch_status_full_workflow(api_url, auth_headers, fresh_firmware_item):
    """Walk an item through the full valid state machine: READY_TO_TEST → TESTING → RELEASED → REVOKED."""
    zip_name = fresh_firmware_item["zip_name"]

    # READY_TO_TEST → TESTING
    resp = requests.patch(
        f"{api_url}/firmware/{zip_name}/status",
        json={"release_status": "TESTING"},
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 200
    assert resp.json()["release_status"] == "TESTING"

    # TESTING → RELEASED
    resp = requests.patch(
        f"{api_url}/firmware/{zip_name}/status",
        json={"release_status": "RELEASED"},
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 200
    assert resp.json()["release_status"] == "RELEASED"

    # RELEASED → REVOKED
    resp = requests.patch(
        f"{api_url}/firmware/{zip_name}/status",
        json={"release_status": "REVOKED"},
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 200
    assert resp.json()["release_status"] == "REVOKED"
