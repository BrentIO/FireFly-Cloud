"""
Tests for PATCH /firmware/{zip_name}/status.
"""

import os
import uuid

import pytest
import requests

from conftest import _upload_and_wait

pytestmark = pytest.mark.firmware_status


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


# ---------------------------------------------------------------------------
# status_history — PATCH response and accumulation
# ---------------------------------------------------------------------------

def test_patch_status_response_includes_status_history(api_url, auth_headers, fresh_firmware_item):
    resp = requests.patch(
        f"{api_url}/firmware/{fresh_firmware_item['zip_name']}/status",
        json={"release_status": "TESTING"},
        headers=auth_headers,
        timeout=10,
    )
    body = resp.json()
    assert "status_history" in body
    assert isinstance(body["status_history"], list)


def test_patch_status_history_grows_after_transition(api_url, auth_headers, fresh_firmware_item):
    """Each PATCH appends one entry; after one transition the list has 2 entries."""
    resp = requests.patch(
        f"{api_url}/firmware/{fresh_firmware_item['zip_name']}/status",
        json={"release_status": "TESTING"},
        headers=auth_headers,
        timeout=10,
    )
    history = resp.json()["status_history"]
    assert len(history) == 2


def test_patch_status_history_new_entry_has_correct_status(api_url, auth_headers, fresh_firmware_item):
    resp = requests.patch(
        f"{api_url}/firmware/{fresh_firmware_item['zip_name']}/status",
        json={"release_status": "TESTING"},
        headers=auth_headers,
        timeout=10,
    )
    history = resp.json()["status_history"]
    assert history[-1]["status"] == "TESTING"


def test_patch_status_history_entry_has_timestamp(api_url, auth_headers, fresh_firmware_item):
    resp = requests.patch(
        f"{api_url}/firmware/{fresh_firmware_item['zip_name']}/status",
        json={"release_status": "TESTING"},
        headers=auth_headers,
        timeout=10,
    )
    for entry in resp.json()["status_history"]:
        assert isinstance(entry["timestamp"], (int, float))
        assert entry["timestamp"] > 0


def test_patch_status_full_workflow_history_has_four_entries(api_url, auth_headers, fresh_firmware_item):
    """Full READY_TO_TEST → TESTING → RELEASED → REVOKED workflow accumulates 4 history entries."""
    zip_name = fresh_firmware_item["zip_name"]

    for new_status in ("TESTING", "RELEASED", "REVOKED"):
        resp = requests.patch(
            f"{api_url}/firmware/{zip_name}/status",
            json={"release_status": new_status},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200

    history = resp.json()["status_history"]
    assert len(history) == 4


def test_patch_status_full_workflow_history_statuses_in_order(api_url, auth_headers, fresh_firmware_item):
    """History entries appear in chronological order matching the transition sequence."""
    zip_name = fresh_firmware_item["zip_name"]

    for new_status in ("TESTING", "RELEASED", "REVOKED"):
        resp = requests.patch(
            f"{api_url}/firmware/{zip_name}/status",
            json={"release_status": new_status},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200

    statuses = [e["status"] for e in resp.json()["status_history"]]
    assert statuses == ["READY_TO_TEST", "TESTING", "RELEASED", "REVOKED"]


# ---------------------------------------------------------------------------
# DEBUG firmware constraints
# ---------------------------------------------------------------------------

def test_patch_status_debug_firmware_cannot_be_released(api_url, auth_headers):
    """DEBUG firmware is blocked from RELEASED in production; allowed in other environments."""
    unique_hex = f"0x{uuid.uuid4().int & 0xFFFFFFFF:08x}"
    item = _upload_and_wait("DEBUG", product_hex=unique_hex)
    zip_name = item["zip_name"]
    is_production = os.environ.get("ENVIRONMENT_NAME", "") == "production"

    try:
        requests.patch(
            f"{api_url}/firmware/{zip_name}/status",
            json={"release_status": "TESTING"},
            headers=auth_headers,
            timeout=10,
        )
        resp = requests.patch(
            f"{api_url}/firmware/{zip_name}/status",
            json={"release_status": "RELEASED"},
            headers=auth_headers,
            timeout=10,
        )
        if is_production:
            assert resp.status_code == 409
            assert "message" in resp.json()
        else:
            assert resp.status_code == 200
    finally:
        requests.delete(f"{api_url}/firmware/{zip_name}", headers=auth_headers, timeout=10)
