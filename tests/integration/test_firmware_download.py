"""
Tests for GET /firmware/{zip_name}/download.
"""

import time
import requests


NONEXISTENT = "00000000-0000-0000-0000-000000000000.zip"


# ---------------------------------------------------------------------------
# Error cases (no upload required)
# ---------------------------------------------------------------------------

def test_download_not_found_returns_404(api_url):
    resp = requests.get(f"{api_url}/firmware/{NONEXISTENT}/download", timeout=10)
    assert resp.status_code == 404


def test_download_not_found_has_message(api_url):
    resp = requests.get(f"{api_url}/firmware/{NONEXISTENT}/download", timeout=10)
    assert "message" in resp.json()


# ---------------------------------------------------------------------------
# Successful pre-signed URL (active firmware)
# ---------------------------------------------------------------------------

def test_download_returns_200(api_url, firmware_item):
    resp = requests.get(
        f"{api_url}/firmware/{firmware_item['zip_name']}/download",
        timeout=10,
    )
    assert resp.status_code == 200


def test_download_response_has_url(api_url, firmware_item):
    resp = requests.get(
        f"{api_url}/firmware/{firmware_item['zip_name']}/download",
        timeout=10,
    )
    assert "url" in resp.json()


def test_download_response_has_expires_in(api_url, firmware_item):
    resp = requests.get(
        f"{api_url}/firmware/{firmware_item['zip_name']}/download",
        timeout=10,
    )
    assert "expires_in" in resp.json()


def test_download_expires_in_is_900(api_url, firmware_item):
    resp = requests.get(
        f"{api_url}/firmware/{firmware_item['zip_name']}/download",
        timeout=10,
    )
    assert resp.json()["expires_in"] == 900


def test_download_url_is_accessible(api_url, firmware_item):
    """The pre-signed URL should return the ZIP without any AWS credentials."""
    resp = requests.get(
        f"{api_url}/firmware/{firmware_item['zip_name']}/download",
        timeout=10,
    )
    url = resp.json()["url"]
    download = requests.get(url, timeout=30)
    assert download.status_code == 200


def test_download_url_returns_zip_content(api_url, firmware_item):
    """Content downloaded via the pre-signed URL should be non-empty."""
    resp = requests.get(
        f"{api_url}/firmware/{firmware_item['zip_name']}/download",
        timeout=10,
    )
    url = resp.json()["url"]
    download = requests.get(url, timeout=30)
    assert len(download.content) > 0


# ---------------------------------------------------------------------------
# Deleted firmware (410)
# ---------------------------------------------------------------------------

def test_download_deleted_firmware_returns_410(api_url, fresh_firmware_item):
    zip_name = fresh_firmware_item["zip_name"]

    # Delete the firmware and wait for the status to update.
    requests.delete(f"{api_url}/firmware/{zip_name}", timeout=10)

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        check = requests.get(f"{api_url}/firmware/{zip_name}", timeout=10)
        if check.status_code == 200 and check.json().get("release_status") == "DELETED":
            break
        time.sleep(2)

    resp = requests.get(f"{api_url}/firmware/{zip_name}/download", timeout=10)
    assert resp.status_code == 410


def test_download_deleted_firmware_has_message(api_url, fresh_firmware_item):
    zip_name = fresh_firmware_item["zip_name"]

    requests.delete(f"{api_url}/firmware/{zip_name}", timeout=10)

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        check = requests.get(f"{api_url}/firmware/{zip_name}", timeout=10)
        if check.status_code == 200 and check.json().get("release_status") == "DELETED":
            break
        time.sleep(2)

    resp = requests.get(f"{api_url}/firmware/{zip_name}/download", timeout=10)
    assert "message" in resp.json()
