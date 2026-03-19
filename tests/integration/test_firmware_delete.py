"""
Tests for DELETE /firmware/{zip_name}.
"""

import time
import requests


NONEXISTENT = "00000000-0000-0000-0000-000000000000.zip"


# ---------------------------------------------------------------------------
# Error cases (no upload required)
# ---------------------------------------------------------------------------

def test_delete_firmware_not_found(api_url, auth_headers):
    resp = requests.delete(f"{api_url}/firmware/{NONEXISTENT}", headers=auth_headers, timeout=10)
    assert resp.status_code == 404


def test_delete_firmware_not_found_has_message(api_url, auth_headers):
    resp = requests.delete(f"{api_url}/firmware/{NONEXISTENT}", headers=auth_headers, timeout=10)
    assert "message" in resp.json()


# ---------------------------------------------------------------------------
# Successful deletion
# ---------------------------------------------------------------------------

def test_delete_firmware_returns_202(api_url, auth_headers, fresh_firmware_item):
    resp = requests.delete(
        f"{api_url}/firmware/{fresh_firmware_item['zip_name']}",
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 202


def test_delete_firmware_response_body(api_url, auth_headers, fresh_firmware_item):
    resp = requests.delete(
        f"{api_url}/firmware/{fresh_firmware_item['zip_name']}",
        headers=auth_headers,
        timeout=10,
    )
    assert resp.json() == {"message": "Deletion initiated"}


# ---------------------------------------------------------------------------
# Conflict cases
# ---------------------------------------------------------------------------

def test_delete_firmware_already_deleted_returns_409(api_url, auth_headers, fresh_firmware_item):
    """Deleting a second time after the first deletion is accepted should return 409."""
    zip_name = fresh_firmware_item["zip_name"]

    # First delete — should succeed
    first = requests.delete(f"{api_url}/firmware/{zip_name}", headers=auth_headers, timeout=10)
    assert first.status_code == 202

    # Wait briefly for S3 event to propagate and DynamoDB status to update.
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        check = requests.get(f"{api_url}/firmware/{zip_name}", headers=auth_headers, timeout=10)
        if check.status_code == 200:
            status = check.json().get("release_status")
            if status in ("DELETED", "REVOKED"):
                break
        time.sleep(2)

    # Second delete — should now be rejected
    second = requests.delete(f"{api_url}/firmware/{zip_name}", headers=auth_headers, timeout=10)
    assert second.status_code == 409


def test_delete_firmware_conflict_has_message(api_url, auth_headers, fresh_firmware_item):
    zip_name = fresh_firmware_item["zip_name"]

    requests.delete(f"{api_url}/firmware/{zip_name}", headers=auth_headers, timeout=10)

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        check = requests.get(f"{api_url}/firmware/{zip_name}", headers=auth_headers, timeout=10)
        if check.status_code == 200 and check.json().get("release_status") in ("DELETED", "REVOKED"):
            break
        time.sleep(2)

    second = requests.delete(f"{api_url}/firmware/{zip_name}", headers=auth_headers, timeout=10)
    assert "message" in second.json()


def test_delete_released_firmware_returns_409(api_url, auth_headers, fresh_firmware_item):
    """REVOKED firmware (reached via RELEASED → REVOKED via PATCH) cannot be deleted."""
    zip_name = fresh_firmware_item["zip_name"]

    # Advance to REVOKED via status transitions
    for status in ("TESTING", "RELEASED", "REVOKED"):
        requests.patch(
            f"{api_url}/firmware/{zip_name}/status",
            json={"release_status": status},
            headers=auth_headers,
            timeout=10,
        )

    resp = requests.delete(f"{api_url}/firmware/{zip_name}", headers=auth_headers, timeout=10)
    assert resp.status_code == 409
