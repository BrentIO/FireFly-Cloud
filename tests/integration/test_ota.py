"""
Tests for GET /ota/{class}/{product_hex}/{application}.

The released_firmware_item fixture requires FIREFLY_FIRMWARE_BUCKET to be set
and the full OTA stack (public S3 bucket, CloudFront, func-api-ota-get) to be
deployed.

Without current_version the endpoint returns all RELEASED versions as a list.
With current_version it returns the next sequential manifest.
"""

import pytest
import requests

pytestmark = pytest.mark.ota

NONEXISTENT_CLASS = "nonexistent"
NONEXISTENT_PRODUCT_HEX = "0x00000000"
NONEXISTENT_APPLICATION = "nonexistent"
OLDER_VERSION = "0.0.01"  # guaranteed to be below any real released version


# ---------------------------------------------------------------------------
# Error cases (no upload required)
# ---------------------------------------------------------------------------

def test_ota_not_found_returns_404(api_url):
    resp = requests.get(
        f"{api_url}/ota/{NONEXISTENT_CLASS}/{NONEXISTENT_PRODUCT_HEX}/{NONEXISTENT_APPLICATION}",
        params={"current_version": OLDER_VERSION},
        timeout=10,
    )
    assert resp.status_code == 404


def test_ota_not_found_has_message(api_url):
    resp = requests.get(
        f"{api_url}/ota/{NONEXISTENT_CLASS}/{NONEXISTENT_PRODUCT_HEX}/{NONEXISTENT_APPLICATION}",
        params={"current_version": OLDER_VERSION},
        timeout=10,
    )
    assert "message" in resp.json()


def test_ota_no_current_version_not_found_returns_404(api_url):
    resp = requests.get(
        f"{api_url}/ota/{NONEXISTENT_CLASS}/{NONEXISTENT_PRODUCT_HEX}/{NONEXISTENT_APPLICATION}",
        timeout=10,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# All-versions response (current_version omitted)
# ---------------------------------------------------------------------------

def test_ota_no_current_version_returns_200(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}/{released_firmware_item['application']}",
        timeout=10,
    )
    assert resp.status_code == 200


def test_ota_no_current_version_has_versions_key(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}/{released_firmware_item['application']}",
        timeout=10,
    )
    assert "versions" in resp.json()


def test_ota_no_current_version_versions_is_list(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}/{released_firmware_item['application']}",
        timeout=10,
    )
    assert isinstance(resp.json()["versions"], list)


def test_ota_no_current_version_contains_released_version(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}/{released_firmware_item['application']}",
        timeout=10,
    )
    versions = [v["version"] for v in resp.json()["versions"]]
    assert released_firmware_item["version"] in versions


# ---------------------------------------------------------------------------
# Valid OTA manifest (current_version provided)
# ---------------------------------------------------------------------------

def test_ota_returns_200_for_released_firmware(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}/{released_firmware_item['application']}",
        params={"current_version": OLDER_VERSION},
        timeout=10,
    )
    assert resp.status_code == 200


def test_ota_manifest_has_type(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}/{released_firmware_item['application']}",
        params={"current_version": OLDER_VERSION},
        timeout=10,
    )
    assert "type" in resp.json()


def test_ota_manifest_has_version(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}/{released_firmware_item['application']}",
        params={"current_version": OLDER_VERSION},
        timeout=10,
    )
    assert "version" in resp.json()


def test_ota_manifest_has_url(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}/{released_firmware_item['application']}",
        params={"current_version": OLDER_VERSION},
        timeout=10,
    )
    assert "app" in resp.json()


def test_ota_manifest_url_is_https(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}/{released_firmware_item['application']}",
        params={"current_version": OLDER_VERSION},
        timeout=10,
    )
    assert resp.json()["app"].startswith("https://")


def test_ota_manifest_version_matches_released(api_url, released_firmware_item):
    resp = requests.get(
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}/{released_firmware_item['application']}",
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
        f"{api_url}/ota/{released_firmware_item['class']}/{released_firmware_item['product_hex']}/{released_firmware_item['application']}",
        params={"current_version": version},
        timeout=10,
    )
    assert resp.status_code == 409
