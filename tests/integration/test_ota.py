"""
Tests for GET /ota/{class}/{product_hex}.

The released_firmware_item fixture requires FIREFLY_FIRMWARE_BUCKET to be set
and the full OTA stack (public S3 bucket, CloudFront, func-api-ota-get) to be
deployed.

Each request passes current_version, which is required by the endpoint.
For the basic manifest tests, we pass a version older than the released item so
the endpoint returns that item as the "next" version.
"""

import pytest
import requests

pytestmark = pytest.mark.ota

NONEXISTENT_CLASS = "nonexistent"
NONEXISTENT_PRODUCT_HEX = "0x00000000"
OLDER_VERSION = "0.0.01"  # guaranteed to be below any real released version


# ---------------------------------------------------------------------------
# Error cases (no upload required)
# ---------------------------------------------------------------------------

def test_ota_missing_current_version_returns_400(api_url):
    resp = requests.get(
        f"{api_url}/ota/{NONEXISTENT_CLASS}/{NONEXISTENT_PRODUCT_HEX}",
        timeout=10,
    )
    assert resp.status_code == 400


def test_ota_not_found_returns_404(api_url):
    resp = requests.get(
        f"{api_url}/ota/{NONEXISTENT_CLASS}/{NONEXISTENT_PRODUCT_HEX}",
        params={"current_version": OLDER_VERSION},
        timeout=10,
    )
    assert resp.status_code == 404


def test_ota_not_found_has_message(api_url):
    resp = requests.get(
        f"{api_url}/ota/{NONEXISTENT_CLASS}/{NONEXISTENT_PRODUCT_HEX}",
        params={"current_version": OLDER_VERSION},
        timeout=10,
    )
    assert "message" in resp.json()


# ---------------------------------------------------------------------------
# Valid OTA manifest (requires released firmware)
# ---------------------------------------------------------------------------

def test_ota_returns_200_for_released_firmware(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}",
        params={"current_version": OLDER_VERSION},
        timeout=10,
    )
    assert resp.status_code == 200


def test_ota_manifest_has_type(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}",
        params={"current_version": OLDER_VERSION},
        timeout=10,
    )
    assert "type" in resp.json()


def test_ota_manifest_has_version(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}",
        params={"current_version": OLDER_VERSION},
        timeout=10,
    )
    assert "version" in resp.json()


def test_ota_manifest_has_url(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}",
        params={"current_version": OLDER_VERSION},
        timeout=10,
    )
    assert "url" in resp.json()


def test_ota_manifest_url_is_https(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}",
        params={"current_version": OLDER_VERSION},
        timeout=10,
    )
    assert resp.json()["url"].startswith("https://")


def test_ota_manifest_version_matches_released(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}",
        params={"current_version": OLDER_VERSION},
        timeout=10,
    )
    assert resp.json()["version"] == released_firmware_item["version"]


def test_ota_returns_409_after_revoke_with_nothing_newer(api_url, auth_headers, fresh_released_firmware_item):
    released_firmware_item = fresh_released_firmware_item
    """
    After the only released firmware is revoked, a device still running that version
    has no viable update path — the endpoint returns 409 Conflict.
    """
    version = released_firmware_item["version"]
    zip_name = released_firmware_item["zip_name"]
    requests.patch(
        f"{api_url}/firmware/{zip_name}/status",
        json={"release_status": "REVOKED"},
        headers=auth_headers,
        timeout=10,
    )
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}",
        params={"current_version": version},
        timeout=10,
    )
    assert resp.status_code == 409
