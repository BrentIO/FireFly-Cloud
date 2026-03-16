"""
Shared fixtures for FireFly integration tests.

Required environment variables:
  FIREFLY_API_URL          Base URL of the API (default: https://api.p5software.com)
  FIREFLY_FIRMWARE_BUCKET  S3 bucket name (required for any test that uploads firmware)
  FIREFLY_UI_URL           Base URL of the UI (required for CORS tests)

Optional environment variables:
  CLEANUP_TEST_RECORDS     Set to any non-empty value to delete test firmware records
                           after the session completes. Deletes all records for
                           product_id 'firefly-integration-test' and '__UNKNOWN_PRODUCT__'.
                           Records in RELEASED state are transitioned to REVOKED first
                           (sets DynamoDB TTL); REVOKED/DELETED records are left for TTL.

AWS credentials must be available via the standard boto3 credential chain
(environment variables, ~/.aws/credentials, IAM role, etc.).
"""

import hashlib
import io
import json
import os
import time
import uuid
import zipfile
from datetime import datetime, timezone

import boto3
import pytest
import requests

API_URL = os.environ.get("FIREFLY_API_URL", "https://api.p5software.com")
FIRMWARE_BUCKET = os.environ.get("FIREFLY_FIRMWARE_BUCKET")
UI_URL = os.environ.get("FIREFLY_UI_URL", "")

# Unique product_id so test records are easily identifiable and filterable.
TEST_PRODUCT_ID = "firefly-integration-test"
TEST_APPLICATION = "test"
TEST_COMMIT = "0000000000000000000000000000000000000000"

# Version strings used by multi-version OTA sequencing fixtures.
# These sort correctly lexicographically: v1 < v2 < v3.
OTA_SEQ_V1 = "1.0.01"
OTA_SEQ_V2 = "2.0.01"
OTA_SEQ_V3 = "3.0.01"


# ---------------------------------------------------------------------------
# ZIP builders — valid firmware
# ---------------------------------------------------------------------------

def _create_test_zip(version: str, product_id: str = TEST_PRODUCT_ID) -> bytes:
    """Build a minimal valid firmware ZIP containing manifest.json and one file."""
    payload = b"FIREFLY_TEST_FIRMWARE_PAYLOAD"
    sha256 = hashlib.sha256(payload).hexdigest()

    manifest = {
        "product_id": product_id,
        "version": version,
        "class": "CONTROLLER",
        "application": TEST_APPLICATION,
        "branch": "main",
        "commit": TEST_COMMIT,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": [{"name": "firmware.bin", "sha256": sha256}],
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("firmware.bin", payload)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# ZIP builders — intentionally invalid, for error-handling tests
# ---------------------------------------------------------------------------

def _create_corrupt_zip() -> bytes:
    """Return bytes that are not a valid ZIP file."""
    return b"THIS IS NOT A VALID ZIP FILE - CORRUPT TEST DATA"


def _create_zip_missing_manifest() -> bytes:
    """Return a valid ZIP that contains no manifest.json."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("firmware.bin", b"FIREFLY_TEST_FIRMWARE_PAYLOAD")
    return buf.getvalue()


def _create_zip_invalid_manifest(missing_field: str, product_id: str = TEST_PRODUCT_ID) -> bytes:
    """Return a valid ZIP whose manifest.json is missing a required field."""
    payload = b"FIREFLY_TEST_FIRMWARE_PAYLOAD"
    sha256 = hashlib.sha256(payload).hexdigest()
    manifest = {
        "product_id": product_id,
        "version": f"error-test-{int(time.time())}",
        "class": "CONTROLLER",
        "application": TEST_APPLICATION,
        "branch": "main",
        "commit": TEST_COMMIT,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": [{"name": "firmware.bin", "sha256": sha256}],
    }
    del manifest[missing_field]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("firmware.bin", payload)
    return buf.getvalue()


def _create_zip_missing_file(product_id: str = TEST_PRODUCT_ID) -> bytes:
    """Return a valid ZIP whose manifest.json references a file not present in the archive."""
    payload = b"FIREFLY_TEST_FIRMWARE_PAYLOAD"
    sha256 = hashlib.sha256(payload).hexdigest()
    manifest = {
        "product_id": product_id,
        "version": f"error-test-{int(time.time())}",
        "class": "CONTROLLER",
        "application": TEST_APPLICATION,
        "branch": "main",
        "commit": TEST_COMMIT,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": [{"name": "firmware.bin", "sha256": sha256}],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        # firmware.bin intentionally omitted
    return buf.getvalue()


def _create_zip_sha256_mismatch(product_id: str = TEST_PRODUCT_ID) -> bytes:
    """Return a valid ZIP where a file's content does not match the SHA256 in the manifest."""
    payload = b"FIREFLY_TEST_FIRMWARE_PAYLOAD"
    wrong_sha256 = hashlib.sha256(b"DIFFERENT CONTENT").hexdigest()
    manifest = {
        "product_id": product_id,
        "version": f"error-test-{int(time.time())}",
        "class": "CONTROLLER",
        "application": TEST_APPLICATION,
        "branch": "main",
        "commit": TEST_COMMIT,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": [{"name": "firmware.bin", "sha256": wrong_sha256}],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("firmware.bin", payload)  # content does not match wrong_sha256
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------------------

def _upload_and_wait(version: str, product_id: str = TEST_PRODUCT_ID, timeout: int = 60) -> dict:
    """Upload a firmware ZIP to S3 and poll the API until the record appears."""
    if not FIRMWARE_BUCKET:
        pytest.skip("FIREFLY_FIRMWARE_BUCKET not set — skipping upload-dependent test")

    zip_bytes = _create_test_zip(version, product_id)
    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=FIRMWARE_BUCKET,
        Key=f"incoming/test-{version}.zip",
        Body=zip_bytes,
    )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = requests.get(
            f"{API_URL}/firmware",
            params={"product_id": product_id, "application": TEST_APPLICATION},
            timeout=10,
        )
        if resp.status_code == 200:
            for item in resp.json().get("items", []):
                if item.get("version") == version:
                    return item
        time.sleep(3)

    pytest.fail(f"Firmware version '{version}' did not appear in API within {timeout}s")


def _upload_and_wait_for_error(
    zip_bytes: bytes,
    filename: str,
    scan_product_id: str,
    timeout: int = 60,
) -> dict:
    """
    Upload ZIP bytes to S3 and poll until an ERROR record with matching filename appears.

    scan_product_id: the product_id to filter by when polling.
      - Pass TEST_PRODUCT_ID when the manifest includes a valid product_id (schema/content errors).
      - Pass '__UNKNOWN_PRODUCT__' when the manifest cannot be parsed at all (corrupt ZIP,
        missing manifest).
    """
    if not FIRMWARE_BUCKET:
        pytest.skip("FIREFLY_FIRMWARE_BUCKET not set — skipping upload-dependent test")

    s3 = boto3.client("s3")
    s3.put_object(Bucket=FIRMWARE_BUCKET, Key=f"incoming/{filename}", Body=zip_bytes)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = requests.get(
            f"{API_URL}/firmware",
            params={"product_id": scan_product_id},
            timeout=10,
        )
        if resp.status_code == 200:
            for item in resp.json().get("items", []):
                if (
                    item.get("release_status") == "ERROR"
                    and item.get("original_name") == filename
                ):
                    return item
        time.sleep(3)

    pytest.fail(f"ERROR record for '{filename}' did not appear in API within {timeout}s")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _release_item(zip_name: str) -> None:
    """Walk a firmware item from READY_TO_TEST through to RELEASED."""
    requests.patch(
        f"{API_URL}/firmware/{zip_name}/status",
        json={"release_status": "TESTING"},
        timeout=10,
    )
    requests.patch(
        f"{API_URL}/firmware/{zip_name}/status",
        json={"release_status": "RELEASED"},
        timeout=10,
    )


def _revoke_item(zip_name: str) -> None:
    requests.patch(
        f"{API_URL}/firmware/{zip_name}/status",
        json={"release_status": "REVOKED"},
        timeout=10,
    )


def _cleanup_product_records(product_id: str) -> None:
    """Delete or revoke all firmware records for the given product_id via the API."""
    resp = requests.get(
        f"{API_URL}/firmware",
        params={"product_id": product_id},
        timeout=10,
    )
    if resp.status_code != 200:
        return
    for item in resp.json().get("items", []):
        zip_name = item["zip_name"]
        status = item.get("release_status")
        if status == "RELEASED":
            _revoke_item(zip_name)
        elif status not in {"REVOKED", "DELETED"}:
            requests.delete(f"{API_URL}/firmware/{zip_name}", timeout=10)


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def api_url() -> str:
    return API_URL


@pytest.fixture(scope="session")
def ui_url() -> str:
    if not UI_URL:
        pytest.skip("FIREFLY_UI_URL not set — skipping CORS tests")
    return UI_URL


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_records():
    """
    After the full test session, delete all test firmware records when
    CLEANUP_TEST_RECORDS is set. Covers the fixed test product_id and any
    error records written under '__UNKNOWN_PRODUCT__'.
    Records in RELEASED state are transitioned to REVOKED (sets DynamoDB TTL);
    REVOKED/DELETED records are left for TTL auto-expiry.
    """
    yield
    if not os.environ.get("CLEANUP_TEST_RECORDS"):
        return
    _cleanup_product_records(TEST_PRODUCT_ID)
    _cleanup_product_records("__UNKNOWN_PRODUCT__")


@pytest.fixture(scope="session")
def firmware_item():
    """
    A processed firmware record available for the full test session.
    Read-only tests should use this fixture; tests that modify state should
    use fresh_firmware_item instead.
    """
    version = f"2026.03.s{int(time.time())}"
    item = _upload_and_wait(version)
    yield item
    # Best-effort cleanup — if the item was already deleted by another test, ignore.
    zip_name = item.get("zip_name")
    if zip_name:
        requests.delete(f"{API_URL}/firmware/{zip_name}", timeout=10)


# ---------------------------------------------------------------------------
# Function-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_firmware_item():
    """
    A fresh firmware record created for a single test that modifies state.
    Cleaned up after the test regardless of outcome.
    """
    version = f"2026.03.f{int(time.time())}"
    item = _upload_and_wait(version)
    yield item
    zip_name = item.get("zip_name")
    if zip_name:
        requests.delete(f"{API_URL}/firmware/{zip_name}", timeout=10)


@pytest.fixture
def released_firmware_item():
    """
    A firmware record walked to RELEASED state for a single test.
    Uses a unique product_id per invocation so this fixture is fully isolated
    from stale data left by previous test runs or other concurrent fixtures.
    Cleaned up after the test by transitioning to REVOKED (which sets the DynamoDB TTL).

    Requires FIREFLY_FIRMWARE_BUCKET to be set and the full OTA stack to be deployed,
    including the public S3 bucket. The FIRMWARE_TYPE_MAP on func-api-ota-get must
    include a mapping for the test application (e.g. {"test": "FireFly Test", ...}).
    """
    product_id = f"firefly-inttest-{int(time.time())}"
    version = f"2026.03.r{int(time.time())}"
    item = _upload_and_wait(version, product_id)
    zip_name = item.get("zip_name")

    _release_item(zip_name)
    yield item

    _revoke_item(zip_name)


# ---------------------------------------------------------------------------
# OTA sequencing fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def multi_version_ota_items():
    """
    Creates two isolated products for OTA sequencing tests:
      - product_a: versions v1, v2, v3 — all RELEASED
      - product_b: version v1 only — RELEASED

    Tests that verify the next-version logic and product_id isolation use this fixture.
    Module-scoped so setup runs once for the entire test_ota_sequencing module.
    Cleaned up by revoking all items at teardown.
    """
    if not FIRMWARE_BUCKET:
        pytest.skip("FIREFLY_FIRMWARE_BUCKET not set — skipping OTA sequencing tests")

    ts = int(time.time())
    product_a = f"firefly-inttest-a-{ts}"
    product_b = f"firefly-inttest-b-{ts}"

    a_v1 = _upload_and_wait(OTA_SEQ_V1, product_a)
    a_v2 = _upload_and_wait(OTA_SEQ_V2, product_a)
    a_v3 = _upload_and_wait(OTA_SEQ_V3, product_a)
    b_v1 = _upload_and_wait(OTA_SEQ_V1, product_b)

    for item in (a_v1, a_v2, a_v3, b_v1):
        _release_item(item["zip_name"])

    yield {
        "product_a": product_a,
        "product_b": product_b,
        "v1": OTA_SEQ_V1,
        "v2": OTA_SEQ_V2,
        "v3": OTA_SEQ_V3,
        "a_v1": a_v1,
        "a_v2": a_v2,
        "a_v3": a_v3,
        "b_v1": b_v1,
    }

    for item in (a_v1, a_v2, a_v3, b_v1):
        _revoke_item(item["zip_name"])


@pytest.fixture
def revoked_version_ota_items():
    """
    Creates an isolated product with three versions:
      - v1: REVOKED (represents firmware the device may have already installed)
      - v2, v3: RELEASED

    Used to verify that a device on a revoked version still receives the next
    sequential RELEASED version.
    """
    if not FIRMWARE_BUCKET:
        pytest.skip("FIREFLY_FIRMWARE_BUCKET not set — skipping OTA sequencing tests")

    ts = int(time.time())
    product_id = f"firefly-inttest-rev-{ts}"

    item_v1 = _upload_and_wait(OTA_SEQ_V1, product_id)
    item_v2 = _upload_and_wait(OTA_SEQ_V2, product_id)
    item_v3 = _upload_and_wait(OTA_SEQ_V3, product_id)

    for item in (item_v1, item_v2, item_v3):
        _release_item(item["zip_name"])

    _revoke_item(item_v1["zip_name"])

    yield {
        "product_id": product_id,
        "v1": OTA_SEQ_V1,
        "v2": OTA_SEQ_V2,
        "v3": OTA_SEQ_V3,
        "v1_item": item_v1,
        "v2_item": item_v2,
        "v3_item": item_v3,
    }

    # v1 is already revoked; revoke v2 and v3.
    for item in (item_v2, item_v3):
        _revoke_item(item["zip_name"])
