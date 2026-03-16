"""
Tests for sequential OTA version delivery via GET /ota/{product_id}/{application}.

The multi_version_ota_items fixture (module-scoped) creates:
  - product_a: firmware versions 1.0.01, 2.0.01, 3.0.01 — all RELEASED, application="test"
  - product_b: firmware version 1.0.01 only — RELEASED, application="test"

The revoked_version_ota_items fixture (function-scoped) creates:
  - a product with versions 1.0.01 (REVOKED), 2.0.01, 3.0.01 (both RELEASED)

The multi_application_ota_items fixture (module-scoped) creates:
  - one product_id with application="test":       versions 1.0.01, 2.0.01, 3.0.01 — all RELEASED
  - one product_id with application="test2": version 1.0.01 only — RELEASED

All fixtures use unique product_ids per invocation for full test isolation.

Requires:
  FIREFLY_FIRMWARE_BUCKET to be set and the full OTA stack deployed.
  FIRMWARE_TYPE_MAP on func-api-ota-get must include mappings for both
  'test' and 'test2' applications
  (e.g. {"test": "FireFly Test", "test2": "FireFly Test 2"}).
"""

import requests


# ---------------------------------------------------------------------------
# current_version required
# ---------------------------------------------------------------------------

def test_missing_current_version_returns_400(api_url):
    resp = requests.get(
        f"{api_url}/ota/firefly-does-not-exist/test",
        timeout=10,
    )
    assert resp.status_code == 400


def test_missing_current_version_has_message(api_url):
    resp = requests.get(
        f"{api_url}/ota/firefly-does-not-exist/test",
        timeout=10,
    )
    assert "message" in resp.json()


# ---------------------------------------------------------------------------
# Sequential version delivery — product_a (v1, v2, v3 all RELEASED)
# ---------------------------------------------------------------------------

def test_oldest_version_receives_next(api_url, multi_version_ota_items):
    """Device on v1 should receive v2, not v3."""
    d = multi_version_ota_items
    resp = requests.get(
        f"{api_url}/ota/{d['product_a']}/test",
        params={"current_version": d["v1"]},
        timeout=10,
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == d["v2"]


def test_middle_version_receives_next(api_url, multi_version_ota_items):
    """Device on v2 should receive v3."""
    d = multi_version_ota_items
    resp = requests.get(
        f"{api_url}/ota/{d['product_a']}/test",
        params={"current_version": d["v2"]},
        timeout=10,
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == d["v3"]


def test_latest_version_receives_200_with_same_version(api_url, multi_version_ota_items):
    """Device on v3 (the latest) should receive 200 with v3 — no update triggered."""
    d = multi_version_ota_items
    resp = requests.get(
        f"{api_url}/ota/{d['product_a']}/test",
        params={"current_version": d["v3"]},
        timeout=10,
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == d["v3"]


def test_manifest_has_required_fields(api_url, multi_version_ota_items):
    d = multi_version_ota_items
    resp = requests.get(
        f"{api_url}/ota/{d['product_a']}/test",
        params={"current_version": d["v1"]},
        timeout=10,
    )
    body = resp.json()
    assert "type" in body
    assert "version" in body
    assert "url" in body


def test_manifest_url_is_https(api_url, multi_version_ota_items):
    d = multi_version_ota_items
    resp = requests.get(
        f"{api_url}/ota/{d['product_a']}/test",
        params={"current_version": d["v1"]},
        timeout=10,
    )
    assert resp.json()["url"].startswith("https://")


# ---------------------------------------------------------------------------
# Product isolation — product_b (v1 only RELEASED)
# ---------------------------------------------------------------------------

def test_product_b_returns_its_own_firmware(api_url, multi_version_ota_items):
    """
    product_b has only one version (v1). When queried with current_version below v1,
    it should return its own v1 — not firmware from product_a.
    """
    d = multi_version_ota_items
    resp = requests.get(
        f"{api_url}/ota/{d['product_b']}/test",
        params={"current_version": "0.0.01"},
        timeout=10,
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == d["v1"]


def test_product_b_at_latest_returns_same_version(api_url, multi_version_ota_items):
    """
    product_b is on its only version (v1). No newer version exists, so the endpoint
    returns 200 with v1 (no update). This also confirms product_a's v2/v3 are not visible.
    """
    d = multi_version_ota_items
    resp = requests.get(
        f"{api_url}/ota/{d['product_b']}/test",
        params={"current_version": d["v1"]},
        timeout=10,
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == d["v1"]


def test_unknown_product_returns_404(api_url):
    resp = requests.get(
        f"{api_url}/ota/firefly-does-not-exist/test",
        params={"current_version": "1.0.01"},
        timeout=10,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Revoked current version
# ---------------------------------------------------------------------------

def test_revoked_current_version_returns_next_released(api_url, revoked_version_ota_items):
    """
    Device is running v1, which has been REVOKED. v2 and v3 are RELEASED.
    The endpoint should return v2 (next sequential RELEASED version).
    """
    d = revoked_version_ota_items
    resp = requests.get(
        f"{api_url}/ota/{d['product_id']}/test",
        params={"current_version": d["v1"]},
        timeout=10,
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == d["v2"]


def test_revoked_current_version_does_not_return_latest(api_url, revoked_version_ota_items):
    """
    Device on revoked v1 must receive v2 (next), not v3 (latest).
    Ensures sequential delivery is honoured even when current is revoked.
    """
    d = revoked_version_ota_items
    resp = requests.get(
        f"{api_url}/ota/{d['product_id']}/test",
        params={"current_version": d["v1"]},
        timeout=10,
    )
    assert resp.json()["version"] != d["v3"]


def test_latest_revoked_with_nothing_newer_returns_409(api_url, revoked_version_ota_items):
    """
    Device is on v3 (RELEASED). After v3 is revoked, calling with current_version=v3
    should return 409 — running revoked firmware with no newer release available.
    """
    d = revoked_version_ota_items
    # Revoke v3 within this test; v2 is still RELEASED but is OLDER than v3.
    requests.patch(
        f"{api_url}/firmware/{d['v3_item']['zip_name']}/status",
        json={"release_status": "REVOKED"},
        timeout=10,
    )
    resp = requests.get(
        f"{api_url}/ota/{d['product_id']}/test",
        params={"current_version": d["v3"]},
        timeout=10,
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Application isolation — same product_id, two different applications
# ---------------------------------------------------------------------------

def test_test_application_receives_next_version(api_url, multi_application_ota_items):
    """
    product has test/v1, v2, v3 and test2/v1. A device on test/v1
    should receive test/v2 — not v3, and not any test2 firmware.
    """
    d = multi_application_ota_items
    resp = requests.get(
        f"{api_url}/ota/{d['product_id']}/test",
        params={"current_version": d["v1"]},
        timeout=10,
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == d["v2"]


def test_test2_application_at_latest_returns_same_version(api_url, multi_application_ota_items):
    """
    test2 has only v1. A device already on v1 should receive 200 with v1
    (no update available). test's v2 and v3 must not be returned.
    """
    d = multi_application_ota_items
    resp = requests.get(
        f"{api_url}/ota/{d['product_id']}/test2",
        params={"current_version": d["v1"]},
        timeout=10,
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == d["v1"]


def test_test2_application_does_not_receive_test_versions(api_url, multi_application_ota_items):
    """
    Querying the test2 application must never return firmware released
    under the test application, even though they share the same product_id.
    """
    d = multi_application_ota_items
    resp = requests.get(
        f"{api_url}/ota/{d['product_id']}/test2",
        params={"current_version": "0.0.01"},
        timeout=10,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] not in (d["v2"], d["v3"])
