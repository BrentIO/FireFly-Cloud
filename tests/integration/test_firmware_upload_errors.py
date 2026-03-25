"""
Tests for error handling in func-s3-firmware-uploaded.

Each test uploads an intentionally broken ZIP and verifies that an ERROR record
appears in the API with the correct fields. The Lambda writes ERROR records to
DynamoDB (and moves the ZIP to the errors/ S3 prefix) whenever processing fails.

All tests clean up their ERROR record immediately after asserting, since ERROR
records are not covered by the normal per-fixture teardown.
"""

import uuid

import pytest
import requests

pytestmark = pytest.mark.firmware_upload

from conftest import (
    API_URL,
    TEST_PRODUCT_ID,
    _create_corrupt_zip,
    _create_zip_invalid_manifest,
    _create_zip_missing_file,
    _create_zip_missing_manifest,
    _create_zip_sha256_mismatch,
    _upload_and_wait_for_error,
)


def _unique_filename(label: str) -> str:
    return f"error-{label}-{uuid.uuid4().hex[:8]}.zip"


def _delete_error_record(zip_name: str, auth_headers: dict) -> None:
    """Best-effort cleanup of an ERROR record via the API."""
    requests.delete(f"{API_URL}/firmware/{zip_name}", headers=auth_headers, timeout=10)


# ---------------------------------------------------------------------------
# Scenario 1: corrupt ZIP (not a valid ZIP file at all)
# ---------------------------------------------------------------------------

def test_corrupt_zip_creates_error_record(api_url, auth_headers):
    filename = _unique_filename("corrupt")
    item = _upload_and_wait_for_error(
        _create_corrupt_zip(), filename, scan_product_id="__UNKNOWN_PRODUCT__"
    )
    try:
        assert item["release_status"] == "ERROR"
        assert "error" in item
        assert item["original_name"] == filename
    finally:
        _delete_error_record(item["zip_name"], auth_headers)


def test_corrupt_zip_error_message_is_non_empty(api_url, auth_headers):
    filename = _unique_filename("corrupt-msg")
    item = _upload_and_wait_for_error(
        _create_corrupt_zip(), filename, scan_product_id="__UNKNOWN_PRODUCT__"
    )
    try:
        assert item["error"]
    finally:
        _delete_error_record(item["zip_name"], auth_headers)


# ---------------------------------------------------------------------------
# Scenario 2: valid ZIP but manifest.json is absent
# ---------------------------------------------------------------------------

def test_missing_manifest_creates_error_record(api_url, auth_headers):
    filename = _unique_filename("no-manifest")
    item = _upload_and_wait_for_error(
        _create_zip_missing_manifest(), filename, scan_product_id="__UNKNOWN_PRODUCT__"
    )
    try:
        assert item["release_status"] == "ERROR"
        assert "error" in item
        assert item["original_name"] == filename
    finally:
        _delete_error_record(item["zip_name"], auth_headers)


def test_missing_manifest_error_mentions_manifest(api_url, auth_headers):
    filename = _unique_filename("no-manifest-msg")
    item = _upload_and_wait_for_error(
        _create_zip_missing_manifest(), filename, scan_product_id="__UNKNOWN_PRODUCT__"
    )
    try:
        assert "manifest" in item["error"].lower()
    finally:
        _delete_error_record(item["zip_name"], auth_headers)


# ---------------------------------------------------------------------------
# Scenario 3: manifest.json present but missing a required field
# ---------------------------------------------------------------------------

def test_invalid_manifest_missing_field_creates_error_record(api_url, auth_headers):
    filename = _unique_filename("bad-manifest")
    item = _upload_and_wait_for_error(
        _create_zip_invalid_manifest(missing_field="class"),
        filename,
        scan_product_id=TEST_PRODUCT_ID,
    )
    try:
        assert item["release_status"] == "ERROR"
        assert "error" in item
        assert item["original_name"] == filename
    finally:
        _delete_error_record(item["zip_name"], auth_headers)


def test_invalid_manifest_error_identifies_missing_field(api_url, auth_headers):
    filename = _unique_filename("bad-manifest-msg")
    item = _upload_and_wait_for_error(
        _create_zip_invalid_manifest(missing_field="class"),
        filename,
        scan_product_id=TEST_PRODUCT_ID,
    )
    try:
        assert "class" in item["error"]
    finally:
        _delete_error_record(item["zip_name"], auth_headers)


# ---------------------------------------------------------------------------
# Scenario 4: manifest references a file that is not in the ZIP
# ---------------------------------------------------------------------------

def test_missing_file_creates_error_record(api_url, auth_headers):
    filename = _unique_filename("missing-file")
    item = _upload_and_wait_for_error(
        _create_zip_missing_file(),
        filename,
        scan_product_id=TEST_PRODUCT_ID,
    )
    try:
        assert item["release_status"] == "ERROR"
        assert "error" in item
        assert item["original_name"] == filename
    finally:
        _delete_error_record(item["zip_name"], auth_headers)


def test_missing_file_error_identifies_filename(api_url, auth_headers):
    filename = _unique_filename("missing-file-msg")
    item = _upload_and_wait_for_error(
        _create_zip_missing_file(),
        filename,
        scan_product_id=TEST_PRODUCT_ID,
    )
    try:
        assert "firmware.bin" in item["error"]
    finally:
        _delete_error_record(item["zip_name"], auth_headers)


# ---------------------------------------------------------------------------
# Scenario 5: file is present but its content does not match the SHA256
# ---------------------------------------------------------------------------

def test_sha256_mismatch_creates_error_record(api_url, auth_headers):
    filename = _unique_filename("sha256-mismatch")
    item = _upload_and_wait_for_error(
        _create_zip_sha256_mismatch(),
        filename,
        scan_product_id=TEST_PRODUCT_ID,
    )
    try:
        assert item["release_status"] == "ERROR"
        assert "error" in item
        assert item["original_name"] == filename
    finally:
        _delete_error_record(item["zip_name"], auth_headers)


def test_sha256_mismatch_error_identifies_filename(api_url, auth_headers):
    filename = _unique_filename("sha256-mismatch-msg")
    item = _upload_and_wait_for_error(
        _create_zip_sha256_mismatch(),
        filename,
        scan_product_id=TEST_PRODUCT_ID,
    )
    try:
        assert "firmware.bin" in item["error"]
    finally:
        _delete_error_record(item["zip_name"], auth_headers)
