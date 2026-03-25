"""
Tests for GET /firmware and GET /firmware/{zip_name}.
"""

import pytest
import requests

pytestmark = pytest.mark.firmware_get


# ---------------------------------------------------------------------------
# GET /firmware (list)
# ---------------------------------------------------------------------------

def test_list_firmware_returns_200(api_url, auth_headers):
    resp = requests.get(f"{api_url}/firmware", headers=auth_headers, timeout=10)
    assert resp.status_code == 200


def test_list_firmware_response_has_items_key(api_url, auth_headers):
    resp = requests.get(f"{api_url}/firmware", headers=auth_headers, timeout=10)
    assert "items" in resp.json()


def test_list_firmware_items_is_list(api_url, auth_headers):
    resp = requests.get(f"{api_url}/firmware", headers=auth_headers, timeout=10)
    assert isinstance(resp.json()["items"], list)


def test_list_firmware_content_type(api_url, auth_headers):
    resp = requests.get(f"{api_url}/firmware", headers=auth_headers, timeout=10)
    assert "application/json" in resp.headers.get("Content-Type", "")


def test_list_firmware_item_excludes_files_field(api_url, auth_headers, firmware_item):
    resp = requests.get(f"{api_url}/firmware", headers=auth_headers, timeout=10)
    for item in resp.json()["items"]:
        assert "files" not in item, "List response must not include 'files'"


def test_list_firmware_item_excludes_pk_field(api_url, auth_headers, firmware_item):
    resp = requests.get(f"{api_url}/firmware", headers=auth_headers, timeout=10)
    for item in resp.json()["items"]:
        assert "pk" not in item, "List response must not include 'pk'"


def test_list_firmware_item_required_fields(api_url, auth_headers, firmware_item):
    resp = requests.get(f"{api_url}/firmware", headers=auth_headers, timeout=10)
    items = resp.json()["items"]
    assert len(items) > 0, "Expected at least one item after uploading test firmware"
    required = {"product_id", "version", "release_status", "zip_name"}
    for item in items:
        missing = required - item.keys()
        assert not missing, f"Item missing fields: {missing}"


def test_list_firmware_filter_by_product_id(api_url, auth_headers, firmware_item):
    resp = requests.get(
        f"{api_url}/firmware",
        params={"product_id": firmware_item["product_id"]},
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(i["zip_name"] == firmware_item["zip_name"] for i in items)
    for item in items:
        assert item["product_id"] == firmware_item["product_id"]


def test_list_firmware_filter_by_application(api_url, auth_headers, firmware_item):
    resp = requests.get(
        f"{api_url}/firmware",
        params={"application": firmware_item["application"]},
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 200
    for item in resp.json()["items"]:
        assert item["application"] == firmware_item["application"]


def test_list_firmware_filter_by_version(api_url, auth_headers, firmware_item):
    resp = requests.get(
        f"{api_url}/firmware",
        params={"version": firmware_item["version"]},
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    for item in items:
        assert item["version"] == firmware_item["version"]


def test_list_firmware_unknown_product_id_returns_empty(api_url, auth_headers):
    resp = requests.get(
        f"{api_url}/firmware",
        params={"product_id": "does-not-exist-xyz"},
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# GET /firmware/{zip_name}
# ---------------------------------------------------------------------------

def test_get_firmware_item_not_found(api_url, auth_headers):
    resp = requests.get(
        f"{api_url}/firmware/00000000-0000-0000-0000-000000000000.zip",
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 404


def test_get_firmware_item_not_found_has_message(api_url, auth_headers):
    resp = requests.get(
        f"{api_url}/firmware/00000000-0000-0000-0000-000000000000.zip",
        headers=auth_headers,
        timeout=10,
    )
    assert "message" in resp.json()


def test_get_firmware_item_returns_200(api_url, auth_headers, firmware_item):
    resp = requests.get(
        f"{api_url}/firmware/{firmware_item['zip_name']}",
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 200


def test_get_firmware_item_includes_files_field(api_url, auth_headers, firmware_item):
    resp = requests.get(
        f"{api_url}/firmware/{firmware_item['zip_name']}",
        headers=auth_headers,
        timeout=10,
    )
    body = resp.json()
    assert "files" in body
    assert isinstance(body["files"], list)
    assert len(body["files"]) > 0


def test_get_firmware_item_files_have_name_and_sha256(api_url, auth_headers, firmware_item):
    resp = requests.get(
        f"{api_url}/firmware/{firmware_item['zip_name']}",
        headers=auth_headers,
        timeout=10,
    )
    for f in resp.json()["files"]:
        assert "name" in f
        assert "sha256" in f
        assert len(f["sha256"]) == 64


def test_get_firmware_item_excludes_pk_field(api_url, auth_headers, firmware_item):
    resp = requests.get(
        f"{api_url}/firmware/{firmware_item['zip_name']}",
        headers=auth_headers,
        timeout=10,
    )
    assert "pk" not in resp.json()


def test_get_firmware_item_matches_list_entry(api_url, auth_headers, firmware_item):
    """Fields present in the list response should match the single-item response."""
    list_resp = requests.get(
        f"{api_url}/firmware",
        params={"product_id": firmware_item["product_id"]},
        headers=auth_headers,
        timeout=10,
    )
    list_items = {i["zip_name"]: i for i in list_resp.json()["items"]}
    assert firmware_item["zip_name"] in list_items

    item_resp = requests.get(
        f"{api_url}/firmware/{firmware_item['zip_name']}",
        headers=auth_headers,
        timeout=10,
    )
    item = item_resp.json()

    for key, value in list_items[firmware_item["zip_name"]].items():
        assert item.get(key) == value, f"Mismatch on field '{key}'"
