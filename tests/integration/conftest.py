"""
Shared fixtures for FireFly integration tests.

Required environment variables:
  FIREFLY_API_URL          Base URL of the API (default: https://api.p5software.com)
  FIREFLY_FIRMWARE_BUCKET  S3 bucket name (required for any test that uploads firmware)
  FIREFLY_UI_URL           Base URL of the UI (required for CORS tests)

Optional environment variables:
  CLEANUP_TEST_RECORDS     Set to any non-empty value to delete test firmware records
                           after the session completes. Covers all product_ids created
                           during the session (including dynamic per-test IDs) plus the
                           fixed TEST_PRODUCT_ID and '__UNKNOWN_PRODUCT__'. Records in
                           RELEASED state are transitioned to REVOKED first (sets DynamoDB
                           TTL); REVOKED/DELETED records are left for TTL auto-expiry.
  FIREFLY_COGNITO_USER_POOL_ID   Cognito User Pool ID (required for auth tests)
  FIREFLY_COGNITO_CLIENT_ID      Cognito App Client ID (required for auth tests)
  FIREFLY_TEST_USER_EMAIL        Email of the test Cognito user (AdminCreateUser)
  FIREFLY_TEST_USER_PASSWORD     Temporary password of the test Cognito user
  FIREFLY_DYNAMODB_USERS_TABLE_NAME  DynamoDB users table name (required for users mutation tests)

AWS credentials must be available via the standard boto3 credential chain
(environment variables, ~/.aws/credentials, IAM role, etc.).

Fixtures
--------
firmware_item (session)
    A single READY_TO_TEST record for the full session. Use for read-only tests.

fresh_firmware_item (function)
    A fresh READY_TO_TEST record per test. Use for tests that mutate state.

released_firmware_item (function)
    A RELEASED record per test, with its own unique product_id. Revoked at teardown.

multi_version_ota_items (module)
    product_a: v1/v2/v3 RELEASED under application="test"
    product_b: v1 RELEASED under application="test"
    Used for sequential OTA delivery and product isolation tests.

revoked_version_ota_items (function)
    One product: v1 REVOKED, v2/v3 RELEASED, application="test".
    Used for revoked-current-version tests.

multi_application_ota_items (module)
    One product_id with two applications:
      application="test":       v1/v2/v3 RELEASED
      application="test2": v1 RELEASED
    Used to verify that OTA responses are scoped to the requested application.

auth_headers (session)
    {"Authorization": "Bearer <access_token>"} for the test Cognito user.
    Skipped when Cognito env vars are not set.

super_auth_with_dynamo (session)
    Like super_auth_headers but also ensures the CI test user has a DynamoDB
    record with environments ["dev", "production"]. Required for mutation tests
    on POST/PATCH /users that check the caller's environment scope.
    Restores the original DynamoDB state at session teardown.
    Skipped when FIREFLY_DYNAMODB_USERS_TABLE_NAME is not set.

restricted_super_auth (function)
    Same token as super_auth_with_dynamo but CI test user DynamoDB record is
    temporarily restricted to environments ["dev"] only. Used to verify that
    callers cannot grant environment access beyond their own scope.
    Restores original DynamoDB environments after each test.

invited_user (function)
    Creates a test invitation via POST /users; deletes the record at teardown.
    Depends on super_auth_with_dynamo. Skipped when mutation prereqs are absent.
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

COGNITO_USER_POOL_ID        = os.environ.get("FIREFLY_COGNITO_USER_POOL_ID")
COGNITO_CLIENT_ID           = os.environ.get("FIREFLY_COGNITO_CLIENT_ID")
TEST_USER_EMAIL             = os.environ.get("FIREFLY_TEST_USER_EMAIL")
TEST_USER_PASSWORD          = os.environ.get("FIREFLY_TEST_USER_PASSWORD")
DYNAMODB_USERS_TABLE_NAME   = os.environ.get("FIREFLY_DYNAMODB_USERS_TABLE_NAME")

# Unique product_id so test records are easily identifiable and filterable.
TEST_PRODUCT_ID = "firefly-integration-test"
TEST_APPLICATION = "test"
TEST_COMMIT = "0000000000000000000000000000000000000000"

# Version strings used by multi-version OTA sequencing fixtures.
# These sort correctly lexicographically: v1 < v2 < v3.
OTA_SEQ_V1 = "1.0.01"
OTA_SEQ_V2 = "2.0.01"
OTA_SEQ_V3 = "3.0.01"

# Tracks all product_ids created during the session so CLEANUP_TEST_RECORDS
# can delete them even if a fixture's own teardown was skipped due to a failure.
_created_product_ids: set[str] = set()


# ---------------------------------------------------------------------------
# ZIP builders — valid firmware
# ---------------------------------------------------------------------------

def _create_test_zip(
    version: str,
    product_id: str = TEST_PRODUCT_ID,
    application: str = TEST_APPLICATION,
) -> bytes:
    """Build a minimal valid firmware ZIP containing manifest.json and one file."""
    payload = b"FIREFLY_TEST_FIRMWARE_PAYLOAD"
    sha256 = hashlib.sha256(payload).hexdigest()
    partitions_payload = b"FIREFLY_TEST_PARTITIONS_PAYLOAD"
    partitions_sha256 = hashlib.sha256(partitions_payload).hexdigest()

    manifest = {
        "product_id": product_id,
        "version": version,
        "class": "CONTROLLER",
        "application": application,
        "branch": "main",
        "commit": TEST_COMMIT,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": [
            {"name": "firmware.bin", "sha256": sha256},
            {"name": "firmware.partitions.bin", "sha256": partitions_sha256},
        ],
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("firmware.bin", payload)
        zf.writestr("firmware.partitions.bin", partitions_payload)
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
    partitions_payload = b"FIREFLY_TEST_PARTITIONS_PAYLOAD"
    partitions_sha256 = hashlib.sha256(partitions_payload).hexdigest()
    manifest = {
        "product_id": product_id,
        "version": f"error-test-{int(time.time())}",
        "class": "CONTROLLER",
        "application": TEST_APPLICATION,
        "branch": "main",
        "commit": TEST_COMMIT,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": [
            {"name": "firmware.bin", "sha256": sha256},
            {"name": "firmware.partitions.bin", "sha256": partitions_sha256},
        ],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("firmware.partitions.bin", partitions_payload)
        # firmware.bin intentionally omitted
    return buf.getvalue()


def _create_zip_sha256_mismatch(product_id: str = TEST_PRODUCT_ID) -> bytes:
    """Return a valid ZIP where a file's content does not match the SHA256 in the manifest."""
    payload = b"FIREFLY_TEST_FIRMWARE_PAYLOAD"
    wrong_sha256 = hashlib.sha256(b"DIFFERENT CONTENT").hexdigest()
    partitions_payload = b"FIREFLY_TEST_PARTITIONS_PAYLOAD"
    partitions_sha256 = hashlib.sha256(partitions_payload).hexdigest()
    manifest = {
        "product_id": product_id,
        "version": f"error-test-{int(time.time())}",
        "class": "CONTROLLER",
        "application": TEST_APPLICATION,
        "branch": "main",
        "commit": TEST_COMMIT,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": [
            {"name": "firmware.bin", "sha256": wrong_sha256},
            {"name": "firmware.partitions.bin", "sha256": partitions_sha256},
        ],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("firmware.bin", payload)  # content does not match wrong_sha256
        zf.writestr("firmware.partitions.bin", partitions_payload)
    return buf.getvalue()


def _create_zip_missing_partitions(product_id: str = TEST_PRODUCT_ID) -> bytes:
    """Return a valid ZIP whose manifest.json has no partitions.bin entry."""
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
        zf.writestr("firmware.bin", payload)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------------------

def _upload_and_wait(
    version: str,
    product_id: str = TEST_PRODUCT_ID,
    application: str = TEST_APPLICATION,
    timeout: int = 60,
) -> dict:
    """Upload a firmware ZIP to S3 and poll the API until the record appears."""
    if not FIRMWARE_BUCKET:
        pytest.skip("FIREFLY_FIRMWARE_BUCKET not set — skipping upload-dependent test")

    zip_bytes = _create_test_zip(version, product_id, application)
    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=FIRMWARE_BUCKET,
        Key=f"incoming/test-{version}.zip",
        Body=zip_bytes,
    )

    headers = _get_fixture_auth()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = requests.get(
            f"{API_URL}/firmware",
            params={"product_id": product_id, "application": application},
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            for item in resp.json().get("items", []):
                if item.get("version") == version:
                    return item
        time.sleep(1)

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

    headers = _get_fixture_auth()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = requests.get(
            f"{API_URL}/firmware",
            params={"product_id": scan_product_id},
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            for item in resp.json().get("items", []):
                if (
                    item.get("release_status") == "ERROR"
                    and item.get("original_name") == filename
                ):
                    return item
        time.sleep(1)

    pytest.fail(f"ERROR record for '{filename}' did not appear in API within {timeout}s")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _auth_session_headers() -> dict:
    """
    Return auth headers for intra-test API calls (state setup/teardown).

    These calls happen inside fixtures, not directly in tests, so we
    obtain a fresh token here using the same env vars as the auth_headers
    fixture.  Returns an empty dict when auth env vars are absent so that
    non-auth test runs still work.
    """
    if not all([COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, TEST_USER_EMAIL, TEST_USER_PASSWORD]):
        return {}
    try:
        import boto3 as _boto3
        cognito = _boto3.client("cognito-idp")
        resp = cognito.admin_initiate_auth(
            UserPoolId=COGNITO_USER_POOL_ID,
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": TEST_USER_EMAIL,
                "PASSWORD": TEST_USER_PASSWORD,
            },
        )
        token = resp["AuthenticationResult"]["AccessToken"]
        return {"Authorization": f"Bearer {token}"}
    except Exception:
        return {}

# Lazy-loaded auth headers for fixture-internal calls (one token per session)
_FIXTURE_AUTH: dict | None = None


def _get_fixture_auth() -> dict:
    global _FIXTURE_AUTH
    if _FIXTURE_AUTH is None:
        _FIXTURE_AUTH = _auth_session_headers()
    return _FIXTURE_AUTH


def _release_item(zip_name: str) -> None:
    """Walk a firmware item from READY_TO_TEST through to RELEASED."""
    headers = _get_fixture_auth()
    requests.patch(
        f"{API_URL}/firmware/{zip_name}/status",
        json={"release_status": "TESTING"},
        headers=headers,
        timeout=10,
    )
    requests.patch(
        f"{API_URL}/firmware/{zip_name}/status",
        json={"release_status": "RELEASED"},
        headers=headers,
        timeout=10,
    )


def _revoke_item(zip_name: str) -> None:
    requests.patch(
        f"{API_URL}/firmware/{zip_name}/status",
        json={"release_status": "REVOKED"},
        headers=_get_fixture_auth(),
        timeout=10,
    )


def _cleanup_product_records(product_id: str) -> None:
    """Delete or revoke all firmware records for the given product_id via the API."""
    headers = _get_fixture_auth()
    resp = requests.get(
        f"{API_URL}/firmware",
        params={"product_id": product_id},
        headers=headers,
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
            requests.delete(f"{API_URL}/firmware/{zip_name}", headers=headers, timeout=10)


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


@pytest.fixture(scope="session")
def auth_headers() -> dict:
    """
    Return {"Authorization": "Bearer <access_token>"} for the test Cognito user.

    Uses AdminInitiateAuth with ADMIN_USER_PASSWORD_AUTH flow — requires AWS
    admin credentials (available in CI via IAM role or env vars) and the test
    user to exist in the User Pool via AdminCreateUser.

    Skipped when any required env var is absent.
    """
    if not all([COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, TEST_USER_EMAIL, TEST_USER_PASSWORD]):
        pytest.skip(
            "Cognito auth env vars not set "
            "(FIREFLY_COGNITO_USER_POOL_ID, FIREFLY_COGNITO_CLIENT_ID, "
            "FIREFLY_TEST_USER_EMAIL, FIREFLY_TEST_USER_PASSWORD) "
            "— skipping auth-dependent tests"
        )

    cognito = boto3.client("cognito-idp")
    resp = cognito.admin_initiate_auth(
        UserPoolId=COGNITO_USER_POOL_ID,
        ClientId=COGNITO_CLIENT_ID,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters={
            "USERNAME": TEST_USER_EMAIL,
            "PASSWORD": TEST_USER_PASSWORD,
        },
    )
    access_token = resp["AuthenticationResult"]["AccessToken"]
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture(scope="session")
def super_auth_headers() -> dict:
    """
    Return {"Authorization": "Bearer <access_token>"} for the test Cognito user
    after temporarily adding them to the super_users group.

    Setup:  adds CI test user to super_users, then obtains a fresh access token
            (so the token carries the super_users group claim).
    Teardown: removes CI test user from super_users.

    Skipped when any required Cognito env var is absent.
    """
    if not all([COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, TEST_USER_EMAIL, TEST_USER_PASSWORD]):
        pytest.skip(
            "Cognito auth env vars not set "
            "(FIREFLY_COGNITO_USER_POOL_ID, FIREFLY_COGNITO_CLIENT_ID, "
            "FIREFLY_TEST_USER_EMAIL, FIREFLY_TEST_USER_PASSWORD) "
            "— skipping super-user tests"
        )

    cognito = boto3.client("cognito-idp")
    super_group = "super_users"

    # Resolve the Cognito Username (may differ from email for federated users).
    response = cognito.list_users(
        UserPoolId=COGNITO_USER_POOL_ID,
        Filter=f'email = "{TEST_USER_EMAIL}"',
    )
    users = response.get("Users", [])
    if not users:
        pytest.skip(f"Test user '{TEST_USER_EMAIL}' not found in Cognito user pool")
    cognito_username = users[0]["Username"]

    cognito.admin_add_user_to_group(
        UserPoolId=COGNITO_USER_POOL_ID,
        Username=cognito_username,
        GroupName=super_group,
    )

    try:
        # Obtain a fresh token after the group membership change so that the
        # cognito:groups claim includes super_users.
        resp = cognito.admin_initiate_auth(
            UserPoolId=COGNITO_USER_POOL_ID,
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": TEST_USER_EMAIL,
                "PASSWORD": TEST_USER_PASSWORD,
            },
        )
        access_token = resp["AuthenticationResult"]["AccessToken"]
        yield {"Authorization": f"Bearer {access_token}"}
    finally:
        cognito.admin_remove_user_from_group(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=cognito_username,
            GroupName=super_group,
        )


@pytest.fixture(scope="session")
def super_auth_with_dynamo():
    """
    Like super_auth_headers but also ensures the CI test user has a DynamoDB
    record with environments ["dev", "production"]. Required for POST/PATCH /users
    mutation tests where the lambda checks the caller's environment scope.

    Setup:  adds CI test user to super_users group, upserts DynamoDB record with
            all environments, obtains a fresh access token.
    Teardown: removes from super_users, restores original DynamoDB state.

    Skipped when any required Cognito env var or FIREFLY_DYNAMODB_USERS_TABLE_NAME
    is absent.
    """
    if not all([COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, TEST_USER_EMAIL, TEST_USER_PASSWORD]):
        pytest.skip(
            "Cognito auth env vars not set — skipping users mutation tests"
        )
    if not DYNAMODB_USERS_TABLE_NAME:
        pytest.skip(
            "FIREFLY_DYNAMODB_USERS_TABLE_NAME not set — skipping users mutation tests"
        )

    cognito = boto3.client("cognito-idp")
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(DYNAMODB_USERS_TABLE_NAME)
    super_group = "super_users"
    caller_email = TEST_USER_EMAIL.lower()

    # Resolve Cognito username (email and username may differ).
    response = cognito.list_users(
        UserPoolId=COGNITO_USER_POOL_ID,
        Filter=f'email = "{TEST_USER_EMAIL}"',
    )
    users = response.get("Users", [])
    if not users:
        pytest.skip(f"Test user '{TEST_USER_EMAIL}' not found in Cognito user pool")
    cognito_username = users[0]["Username"]

    # Snapshot original DynamoDB record so we can restore it at teardown.
    resp = table.get_item(Key={"email": caller_email})
    original_item = resp.get("Item")

    # Upsert record with all environments so the caller can grant any env.
    table.put_item(Item={
        "email": caller_email,
        "environments": ["dev", "production"],
        "invited_by": "ci-integration-test",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    cognito.admin_add_user_to_group(
        UserPoolId=COGNITO_USER_POOL_ID,
        Username=cognito_username,
        GroupName=super_group,
    )

    try:
        resp = cognito.admin_initiate_auth(
            UserPoolId=COGNITO_USER_POOL_ID,
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": TEST_USER_EMAIL,
                "PASSWORD": TEST_USER_PASSWORD,
            },
        )
        access_token = resp["AuthenticationResult"]["AccessToken"]
        yield {"Authorization": f"Bearer {access_token}"}
    finally:
        cognito.admin_remove_user_from_group(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=cognito_username,
            GroupName=super_group,
        )
        if original_item:
            table.put_item(Item=original_item)
        else:
            table.delete_item(Key={"email": caller_email})


@pytest.fixture
def restricted_super_auth(super_auth_with_dynamo):
    """
    Same token as super_auth_with_dynamo but the CI test user's DynamoDB record
    is temporarily restricted to environments ["dev"] only.

    Used to verify that callers cannot grant environment access beyond their own
    scope (e.g. caller with only "dev" cannot invite/patch a user into "production").

    Restores the original environments after the test regardless of outcome.
    """
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(DYNAMODB_USERS_TABLE_NAME)
    caller_email = TEST_USER_EMAIL.lower()

    resp = table.get_item(Key={"email": caller_email})
    original_envs = resp.get("Item", {}).get("environments", ["dev", "production"])

    table.update_item(
        Key={"email": caller_email},
        UpdateExpression="SET environments = :envs",
        ExpressionAttributeValues={":envs": ["dev"]},
    )

    try:
        yield super_auth_with_dynamo
    finally:
        table.update_item(
            Key={"email": caller_email},
            UpdateExpression="SET environments = :envs",
            ExpressionAttributeValues={":envs": original_envs},
        )


@pytest.fixture
def invited_user(api_url, super_auth_with_dynamo):
    """
    Create a test user invitation via POST /users; delete at teardown.

    Yields the invited email address as a string. The invited user exists only
    in DynamoDB (has not signed in), so GET /users returns them with
    status="INVITED" and is_super=False.
    """
    test_email = f"firefly-inttest-{int(time.time())}@example.com"
    resp = requests.post(
        f"{api_url}/users",
        json={"email": test_email, "environments": ["dev"]},
        headers=super_auth_with_dynamo,
        timeout=10,
    )
    if resp.status_code != 201:
        pytest.fail(
            f"invited_user fixture: POST /users returned {resp.status_code}: {resp.text}"
        )
    yield test_email
    requests.delete(
        f"{api_url}/users/{requests.utils.quote(test_email, safe='')}",
        headers=super_auth_with_dynamo,
        timeout=10,
    )


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_records():
    """
    After the full test session, delete all test firmware records when
    CLEANUP_TEST_RECORDS is set. Covers every product_id created during the
    session (registered in _created_product_ids by each fixture) plus the
    fixed TEST_PRODUCT_ID and '__UNKNOWN_PRODUCT__'.
    Records in RELEASED state are transitioned to REVOKED (sets DynamoDB TTL);
    REVOKED/DELETED records are left for TTL auto-expiry.
    """
    yield
    if not os.environ.get("CLEANUP_TEST_RECORDS"):
        return
    all_products = _created_product_ids | {TEST_PRODUCT_ID, "__UNKNOWN_PRODUCT__"}
    for product_id in all_products:
        _cleanup_product_records(product_id)


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


@pytest.fixture(scope="module")
def released_firmware_item():
    """
    A firmware record walked to RELEASED state, shared across all tests in the module.
    Uses a unique product_id so it is isolated from stale data left by other runs.
    Cleaned up after the module by transitioning to REVOKED (which sets the DynamoDB TTL).

    Use this fixture for read-only OTA tests. Tests that mutate the release status
    (e.g. revoking the item) must use fresh_released_firmware_item instead.

    Requires FIREFLY_FIRMWARE_BUCKET to be set and the full OTA stack to be deployed,
    including the public S3 bucket. The FIRMWARE_TYPE_MAP on func-api-ota-get must
    include a mapping for the test application (e.g. {"test": "FireFly Test", ...}).
    """
    product_id = f"firefly-inttest-{int(time.time())}"
    _created_product_ids.add(product_id)
    version = f"2026.03.r{int(time.time())}"
    item = _upload_and_wait(version, product_id)
    zip_name = item.get("zip_name")

    _release_item(zip_name)
    yield item

    _revoke_item(zip_name)


@pytest.fixture
def fresh_released_firmware_item():
    """
    A firmware record walked to RELEASED state for a single test that mutates it.
    Uses a unique product_id per invocation for full isolation.
    Cleaned up after the test by transitioning to REVOKED (which sets the DynamoDB TTL).

    Use this fixture when the test will change the release status (e.g. revoke the item).
    Read-only tests should use released_firmware_item instead.
    """
    product_id = f"firefly-inttest-{int(time.time())}"
    _created_product_ids.add(product_id)
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
      - product_a: versions v1, v2, v3 — all RELEASED under application="test"
      - product_b: version v1 only — RELEASED under application="test"

    Tests that verify the next-version logic and product_id isolation use this fixture.
    Module-scoped so setup runs once for the entire test_ota_sequencing module.
    Cleaned up by revoking all items at teardown.
    """
    if not FIRMWARE_BUCKET:
        pytest.skip("FIREFLY_FIRMWARE_BUCKET not set — skipping OTA sequencing tests")

    ts = int(time.time())
    product_a = f"firefly-inttest-a-{ts}"
    product_b = f"firefly-inttest-b-{ts}"
    _created_product_ids.add(product_a)
    _created_product_ids.add(product_b)

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


@pytest.fixture(scope="module")
def revoked_version_ota_items():
    """
    Creates an isolated product with three versions, shared across all tests in the module:
      - v1: REVOKED (represents firmware the device may have already installed)
      - v2, v3: RELEASED

    Used to verify that a device on a revoked version still receives the next
    sequential RELEASED version. Tests that further mutate v2/v3 status must use
    fresh_revoked_version_ota_items instead.
    """
    if not FIRMWARE_BUCKET:
        pytest.skip("FIREFLY_FIRMWARE_BUCKET not set — skipping OTA sequencing tests")

    ts = int(time.time())
    product_id = f"firefly-inttest-rev-{ts}"
    _created_product_ids.add(product_id)

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


@pytest.fixture
def fresh_revoked_version_ota_items():
    """
    Creates an isolated product with three versions for a single test that mutates state:
      - v1: REVOKED
      - v2, v3: RELEASED

    Use this fixture when the test will further change v2 or v3 status (e.g. revoking v3).
    Read-only tests should use revoked_version_ota_items instead.
    """
    if not FIRMWARE_BUCKET:
        pytest.skip("FIREFLY_FIRMWARE_BUCKET not set — skipping OTA sequencing tests")

    ts = int(time.time())
    product_id = f"firefly-inttest-rev-{ts}"
    _created_product_ids.add(product_id)

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


@pytest.fixture(scope="module")
def multi_application_ota_items():
    """
    Creates one product_id with firmware for two different applications:
      - application="test":       versions v1, v2, v3 — all RELEASED
      - application="test2": version v1 only — RELEASED

    Used to verify that the OTA endpoint scopes results to the requested
    application and does not leak firmware across applications on the same
    product_id. Module-scoped so setup runs once per module.
    """
    if not FIRMWARE_BUCKET:
        pytest.skip("FIREFLY_FIRMWARE_BUCKET not set — skipping OTA sequencing tests")

    ts = int(time.time())
    product_id = f"firefly-inttest-app-{ts}"
    _created_product_ids.add(product_id)

    test_v1 = _upload_and_wait(OTA_SEQ_V1, product_id, application="test")
    test_v2 = _upload_and_wait(OTA_SEQ_V2, product_id, application="test")
    test_v3 = _upload_and_wait(OTA_SEQ_V3, product_id, application="test")
    ctrl_v1 = _upload_and_wait(OTA_SEQ_V1, product_id, application="test2")

    for item in (test_v1, test_v2, test_v3, ctrl_v1):
        _release_item(item["zip_name"])

    yield {
        "product_id": product_id,
        "v1": OTA_SEQ_V1,
        "v2": OTA_SEQ_V2,
        "v3": OTA_SEQ_V3,
        "test_v1": test_v1,
        "test_v2": test_v2,
        "test_v3": test_v3,
        "ctrl_v1": ctrl_v1,
    }

    for item in (test_v1, test_v2, test_v3, ctrl_v1):
        _revoke_item(item["zip_name"])
