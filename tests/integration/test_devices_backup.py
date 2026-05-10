"""
Integration tests for device configuration backup endpoints.

  POST   /devices/{uuid}/backup   — store an encrypted FFCE backup (issues #212)
  GET    /devices/{uuid}/backup   — retrieve the stored backup (issue #213)
  DELETE /devices/{uuid}/backup   — remove the backup (issue #214)

Authentication uses the same four device-auth headers as the registration
endpoint: X-Device-UUID, X-Device-Nonce, X-Device-Timestamp, X-Device-Signature.

Required environment variables (in addition to the standard conftest.py set):
  FIREFLY_API_URL               Base URL of the API
  FIREFLY_DEVICES_TABLE_NAME    DynamoDB devices table name (default: firefly-devices)
"""

import base64
import hashlib
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDSA,
    SECP256R1,
    generate_private_key,
)
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.backends import default_backend

# ---------------------------------------------------------------------------
# Helpers (mirror of test_devices.py)
# ---------------------------------------------------------------------------

_TEST_MCU = {
    "model": "ESP32-D0WD-V3",
    "revision": 3,
    "cpu_freq_mhz": 240,
    "cores": 2,
    "flash_chip_size": 16777216,
    "flash_chip_speed": 80000000,
    "flash_chip_mode": "QIO",
    "psram_size": 0,
    "features": ["WiFi-bgn", "BLE", "Embedded-Flash"],
    "idf_version": "v5.3.2",
}

_TEST_NETWORK = [
    {"interface": "wifi", "mac_address": "DE:AD:BE:EF:01:01"},
    {"interface": "wifi_ap", "mac_address": "DE:AD:BE:EF:01:02"},
    {"interface": "bluetooth", "mac_address": "DE:AD:BE:EF:01:03"},
    {"interface": "ethernet", "mac_address": "DE:AD:BE:EF:01:04"},
]

_TEST_PARTITIONS = [
    {"type": 0, "subtype": 0, "address": 36864, "size": 16384, "label": "nvs"},
    {"type": 1, "subtype": 2, "address": 57344, "size": 8192, "label": "phy_init"},
    {"type": 0, "subtype": 16, "address": 65536, "size": 6815744, "label": "app0"},
]

# Minimal valid FFCE blob (magic bytes + padding to resemble a real header)
_VALID_FFCE_BODY = b"FFCE" + b"\x01" + b"\x00" * 32

# Invalid body that does not start with the FFCE magic
_INVALID_BODY = b"not_a_valid_ffce_payload"


def _make_device_payload(test_uuid: str, public_key_b64: str) -> dict:
    return {
        "uuid": test_uuid,
        "product_id": "FFC0806-2505",
        "product_hex": "0x08062505",
        "device_class": "CONTROLLER",
        "public_key": public_key_b64,
        "registering_application": "Hardware-Registration-and-Configuration",
        "registering_version": "9999.99.99",
        "mcu": _TEST_MCU,
        "network": _TEST_NETWORK,
        "partitions": _TEST_PARTITIONS,
    }


def _generate_keypair():
    private_key = generate_private_key(SECP256R1(), default_backend())
    pub = private_key.public_key()
    pub_numbers = pub.public_numbers()
    x = pub_numbers.x.to_bytes(32, "big")
    y = pub_numbers.y.to_bytes(32, "big")
    public_key_b64 = base64.b64encode(b"\x04" + x + y).decode()
    return private_key, public_key_b64


def _now_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _sign_nonce(private_key, nonce: bytes, timestamp: str) -> str:
    msg_digest = hashlib.sha256(nonce + timestamp.encode("ascii")).digest()
    sig = private_key.sign(msg_digest, ECDSA(SHA256()))
    return base64.b64encode(sig).decode()


def _auth_headers(test_uuid: str, private_key, nonce: bytes = None) -> dict:
    """Build the four device-auth headers for a request."""
    if nonce is None:
        nonce = os.urandom(32)
    ts = _now_timestamp()
    sig = _sign_nonce(private_key, nonce, ts)
    return {
        "X-Device-UUID": test_uuid,
        "X-Device-Nonce": base64.b64encode(nonce).decode(),
        "X-Device-Timestamp": ts,
        "X-Device-Signature": sig,
    }


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def registration_key(api_url, auth_headers):
    resp = requests.post(f"{api_url}/registration-keys", headers=auth_headers, timeout=10)
    if resp.status_code != 201:
        pytest.fail(f"registration_key fixture: POST /registration-keys returned {resp.status_code}: {resp.text}")
    yield resp.json()["key"]


@pytest.fixture(scope="module")
def registered_device(api_url, registration_key):
    """Register a test device; yield (test_uuid, private_key, public_key_b64).

    Teardown attempts to delete any backup stored during the module, then
    removes the device record from DynamoDB.
    """
    private_key, public_key_b64 = _generate_keypair()
    test_uuid = str(uuid.uuid4())
    payload = _make_device_payload(test_uuid, public_key_b64)
    resp = requests.post(
        f"{api_url}/devices/register",
        json=payload,
        headers={"X-Registration-Key": registration_key},
        timeout=10,
    )
    if resp.status_code != 204:
        pytest.fail(f"registered_device fixture: POST /devices/register returned {resp.status_code}: {resp.text}")
    yield test_uuid, private_key, public_key_b64

    # Best-effort: delete any backup stored during the test module
    try:
        requests.delete(
            f"{api_url}/devices/{test_uuid}/backup",
            headers=_auth_headers(test_uuid, private_key),
            timeout=10,
        )
    except Exception:
        pass

    # Remove the device record from DynamoDB
    import boto3
    table_name = os.environ.get("FIREFLY_DEVICES_TABLE_NAME", "firefly-devices")
    try:
        boto3.resource("dynamodb").Table(table_name).delete_item(Key={"uuid": test_uuid})
    except Exception as e:
        print(f"Warning: could not delete test device {test_uuid}: {e}")


# ---------------------------------------------------------------------------
# POST /devices/{uuid}/backup — issue #212
# ---------------------------------------------------------------------------

class TestDevicesBackupPost:

    def test_missing_headers_returns_400(self, api_url, registered_device):
        test_uuid, _, _ = registered_device
        r = requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=_VALID_FFCE_BODY,
            headers={"Content-Type": "application/octet-stream"},
            timeout=10,
        )
        assert r.status_code == 400

    def test_uuid_header_mismatch_returns_403(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        headers = _auth_headers(test_uuid, private_key)
        headers["X-Device-UUID"] = str(uuid.uuid4())
        headers["Content-Type"] = "application/octet-stream"
        r = requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=_VALID_FFCE_BODY,
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 403

    def test_unknown_uuid_returns_401(self, api_url):
        unknown = str(uuid.uuid4())
        private_key, _ = _generate_keypair()
        private_key = private_key  # unregistered key
        headers = _auth_headers(unknown, generate_private_key(SECP256R1(), default_backend()))
        headers["Content-Type"] = "application/octet-stream"
        r = requests.post(
            f"{api_url}/devices/{unknown}/backup",
            data=_VALID_FFCE_BODY,
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 401

    def test_invalid_signature_returns_401(self, api_url, registered_device):
        test_uuid, _, _ = registered_device
        wrong_key = generate_private_key(SECP256R1(), default_backend())
        headers = _auth_headers(test_uuid, wrong_key)
        headers["Content-Type"] = "application/octet-stream"
        r = requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=_VALID_FFCE_BODY,
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 401

    def test_empty_body_returns_400(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        headers = _auth_headers(test_uuid, private_key)
        headers["Content-Type"] = "application/octet-stream"
        r = requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=b"",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 400

    def test_non_ffce_body_returns_400(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        headers = _auth_headers(test_uuid, private_key)
        headers["Content-Type"] = "application/octet-stream"
        r = requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=_INVALID_BODY,
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 400

    def test_oversized_body_returns_413(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        oversized = b"FFCE" + b"\x00" * (512 * 1024 + 1)
        headers = _auth_headers(test_uuid, private_key)
        headers["Content-Type"] = "application/octet-stream"
        r = requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=oversized,
            headers=headers,
            timeout=30,
        )
        assert r.status_code == 413

    def test_valid_backup_returns_200(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        headers = _auth_headers(test_uuid, private_key)
        headers["Content-Type"] = "application/octet-stream"
        r = requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=_VALID_FFCE_BODY,
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200

    def test_valid_backup_response_has_etag(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        headers = _auth_headers(test_uuid, private_key)
        headers["Content-Type"] = "application/octet-stream"
        r = requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=_VALID_FFCE_BODY,
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200
        assert "ETag" in r.headers

    def test_valid_backup_response_has_last_backup_date(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        headers = _auth_headers(test_uuid, private_key)
        headers["Content-Type"] = "application/octet-stream"
        r = requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=_VALID_FFCE_BODY,
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json().get("last_backup_date")

    def test_unchanged_backup_returns_304(self, api_url, registered_device):
        """Posting the same content with If-None-Match returns 304."""
        test_uuid, private_key, _ = registered_device
        # First POST to ensure the backup exists and get the ETag
        headers = _auth_headers(test_uuid, private_key)
        headers["Content-Type"] = "application/octet-stream"
        first = requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=_VALID_FFCE_BODY,
            headers=headers,
            timeout=10,
        )
        assert first.status_code == 200
        etag = first.headers.get("ETag", "").strip('"')
        assert etag

        # POST again with If-None-Match
        headers2 = _auth_headers(test_uuid, private_key)
        headers2["Content-Type"] = "application/octet-stream"
        headers2["If-None-Match"] = f'"{etag}"'
        second = requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=_VALID_FFCE_BODY,
            headers=headers2,
            timeout=10,
        )
        assert second.status_code == 304


# ---------------------------------------------------------------------------
# GET /devices/{uuid}/backup — issue #213
# ---------------------------------------------------------------------------

class TestDevicesBackupGet:

    def test_missing_headers_returns_400(self, api_url, registered_device):
        test_uuid, _, _ = registered_device
        r = requests.get(f"{api_url}/devices/{test_uuid}/backup", timeout=10)
        assert r.status_code == 400

    def test_uuid_header_mismatch_returns_403(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        headers = _auth_headers(test_uuid, private_key)
        headers["X-Device-UUID"] = str(uuid.uuid4())
        r = requests.get(
            f"{api_url}/devices/{test_uuid}/backup",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 403

    def test_unknown_uuid_returns_401(self, api_url):
        unknown = str(uuid.uuid4())
        headers = _auth_headers(unknown, generate_private_key(SECP256R1(), default_backend()))
        r = requests.get(
            f"{api_url}/devices/{unknown}/backup",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 401

    def test_invalid_signature_returns_401(self, api_url, registered_device):
        test_uuid, _, _ = registered_device
        wrong_key = generate_private_key(SECP256R1(), default_backend())
        headers = _auth_headers(test_uuid, wrong_key)
        r = requests.get(
            f"{api_url}/devices/{test_uuid}/backup",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 401

    def test_no_backup_returns_404(self, api_url, registered_device):
        """A freshly registered device with no backup returns 404."""
        # Register a brand-new device for this test so we know it has no backup
        private_key, public_key_b64 = _generate_keypair()
        fresh_uuid = str(uuid.uuid4())

        import boto3
        table_name = os.environ.get("FIREFLY_DEVICES_TABLE_NAME", "firefly-devices")

        # Register directly in DynamoDB without going through the full register flow
        # (avoids consuming a registration key)
        from datetime import datetime, timezone as tz
        boto3.resource("dynamodb").Table(table_name).put_item(Item={
            "uuid": fresh_uuid,
            "product_id": "FFC0806-2505",
            "product_hex": "0x08062505",
            "device_class": "CONTROLLER",
            "public_key": public_key_b64,
            "registration_date": datetime.now(tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

        try:
            headers = _auth_headers(fresh_uuid, private_key)
            r = requests.get(
                f"{api_url}/devices/{fresh_uuid}/backup",
                headers=headers,
                timeout=10,
            )
            assert r.status_code == 404
        finally:
            boto3.resource("dynamodb").Table(table_name).delete_item(Key={"uuid": fresh_uuid})

    def test_valid_get_returns_200(self, api_url, registered_device):
        """After a POST, GET returns 200 with the backup binary."""
        test_uuid, private_key, _ = registered_device
        # Ensure a backup exists
        post_headers = _auth_headers(test_uuid, private_key)
        post_headers["Content-Type"] = "application/octet-stream"
        requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=_VALID_FFCE_BODY,
            headers=post_headers,
            timeout=10,
        )

        get_headers = _auth_headers(test_uuid, private_key)
        r = requests.get(
            f"{api_url}/devices/{test_uuid}/backup",
            headers=get_headers,
            timeout=10,
        )
        assert r.status_code == 200

    def test_valid_get_returns_ffce_content(self, api_url, registered_device):
        """The retrieved backup body starts with the FFCE magic bytes."""
        test_uuid, private_key, _ = registered_device
        post_headers = _auth_headers(test_uuid, private_key)
        post_headers["Content-Type"] = "application/octet-stream"
        requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=_VALID_FFCE_BODY,
            headers=post_headers,
            timeout=10,
        )

        get_headers = _auth_headers(test_uuid, private_key)
        r = requests.get(
            f"{api_url}/devices/{test_uuid}/backup",
            headers=get_headers,
            timeout=10,
        )
        assert r.status_code == 200
        assert r.content[:4] == b"FFCE"

    def test_valid_get_response_has_etag(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        post_headers = _auth_headers(test_uuid, private_key)
        post_headers["Content-Type"] = "application/octet-stream"
        requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=_VALID_FFCE_BODY,
            headers=post_headers,
            timeout=10,
        )

        get_headers = _auth_headers(test_uuid, private_key)
        r = requests.get(
            f"{api_url}/devices/{test_uuid}/backup",
            headers=get_headers,
            timeout=10,
        )
        assert r.status_code == 200
        assert "ETag" in r.headers


# ---------------------------------------------------------------------------
# DELETE /devices/{uuid}/backup — issue #214
# ---------------------------------------------------------------------------

class TestDevicesBackupDelete:

    def test_missing_headers_returns_400(self, api_url, registered_device):
        test_uuid, _, _ = registered_device
        r = requests.delete(f"{api_url}/devices/{test_uuid}/backup", timeout=10)
        assert r.status_code == 400

    def test_uuid_header_mismatch_returns_403(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        headers = _auth_headers(test_uuid, private_key)
        headers["X-Device-UUID"] = str(uuid.uuid4())
        r = requests.delete(
            f"{api_url}/devices/{test_uuid}/backup",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 403

    def test_unknown_uuid_returns_401(self, api_url):
        unknown = str(uuid.uuid4())
        headers = _auth_headers(unknown, generate_private_key(SECP256R1(), default_backend()))
        r = requests.delete(
            f"{api_url}/devices/{unknown}/backup",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 401

    def test_invalid_signature_returns_401(self, api_url, registered_device):
        test_uuid, _, _ = registered_device
        wrong_key = generate_private_key(SECP256R1(), default_backend())
        headers = _auth_headers(test_uuid, wrong_key)
        r = requests.delete(
            f"{api_url}/devices/{test_uuid}/backup",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 401

    def test_delete_existing_backup_returns_200(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        # Store a backup first
        post_headers = _auth_headers(test_uuid, private_key)
        post_headers["Content-Type"] = "application/octet-stream"
        requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=_VALID_FFCE_BODY,
            headers=post_headers,
            timeout=10,
        )

        del_headers = _auth_headers(test_uuid, private_key)
        r = requests.delete(
            f"{api_url}/devices/{test_uuid}/backup",
            headers=del_headers,
            timeout=10,
        )
        assert r.status_code == 200

    def test_delete_returns_200_when_no_backup_exists(self, api_url, registered_device):
        """DELETE is idempotent — returns 200 even if no backup is stored."""
        test_uuid, private_key, _ = registered_device
        # Ensure no backup exists by deleting first (idempotent)
        requests.delete(
            f"{api_url}/devices/{test_uuid}/backup",
            headers=_auth_headers(test_uuid, private_key),
            timeout=10,
        )
        # Delete again — should still be 200
        r = requests.delete(
            f"{api_url}/devices/{test_uuid}/backup",
            headers=_auth_headers(test_uuid, private_key),
            timeout=10,
        )
        assert r.status_code == 200

    def test_delete_removes_backup_from_get(self, api_url, registered_device):
        """After DELETE, a subsequent GET returns 404."""
        test_uuid, private_key, _ = registered_device
        # Store a backup
        post_headers = _auth_headers(test_uuid, private_key)
        post_headers["Content-Type"] = "application/octet-stream"
        requests.post(
            f"{api_url}/devices/{test_uuid}/backup",
            data=_VALID_FFCE_BODY,
            headers=post_headers,
            timeout=10,
        )
        # Delete it
        requests.delete(
            f"{api_url}/devices/{test_uuid}/backup",
            headers=_auth_headers(test_uuid, private_key),
            timeout=10,
        )
        # GET should now 404
        r = requests.get(
            f"{api_url}/devices/{test_uuid}/backup",
            headers=_auth_headers(test_uuid, private_key),
            timeout=10,
        )
        assert r.status_code == 404
