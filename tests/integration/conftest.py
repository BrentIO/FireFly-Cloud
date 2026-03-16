"""
Shared fixtures for FireFly integration tests.

Required environment variables:
  FIREFLY_API_URL          Base URL of the API (default: https://api.p5software.com)
  FIREFLY_FIRMWARE_BUCKET  S3 bucket name (required for any test that uploads firmware)
  FIREFLY_UI_URL           Base URL of the UI (required for CORS tests)

AWS credentials must be available via the standard boto3 credential chain
(environment variables, ~/.aws/credentials, IAM role, etc.).
"""

import hashlib
import io
import json
import os
import time
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
        "commit": "0000000000000000000000000000000000000000",
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": [{"name": "firmware.bin", "sha256": sha256}],
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("firmware.bin", payload)
    return buf.getvalue()


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


@pytest.fixture(scope="session")
def api_url() -> str:
    return API_URL


@pytest.fixture(scope="session")
def ui_url() -> str:
    if not UI_URL:
        pytest.skip("FIREFLY_UI_URL not set — skipping CORS tests")
    return UI_URL


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

    # Walk to RELEASED
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
    yield item

    # Cleanup: transition to REVOKED which sets the DynamoDB TTL.
    requests.patch(
        f"{API_URL}/firmware/{zip_name}/status",
        json={"release_status": "REVOKED"},
        timeout=10,
    )
