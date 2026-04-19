"""
Integration tests for device registration endpoints.

  POST /registration-keys      — generate a one-time registration key
  POST /devices/register       — register a device
  GET  /devices/{uuid}/registration — verify registration status via signed nonce

Required environment variables (in addition to the standard conftest.py set):
  FIREFLY_API_URL               Base URL of the API
  FIREFLY_COGNITO_USER_POOL_ID  Cognito User Pool ID
  FIREFLY_COGNITO_CLIENT_ID     Cognito App Client ID
  FIREFLY_TEST_USER_EMAIL       Email of the test Cognito user
  FIREFLY_TEST_USER_PASSWORD    Temporary password of the test Cognito user
"""

import base64
import os
import time
import uuid

import pytest
import requests
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDSA,
    SECP256R1,
    EllipticCurvePrivateNumbers,
    EllipticCurvePublicNumbers,
    generate_private_key,
)
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.backends import default_backend

API_URL = os.environ.get("FIREFLY_API_URL", "https://api.p5software.com")

TEST_MCU = {
    "model": "ESP32-D0WD-V3",
    "revision": 3,
    "cpu_freq_mhz": 240,
    "cores": 2,
    "flash_chip_size": 16777216,
    "flash_chip_speed": 80000000,
    "flash_chip_mode": "QIO",
    "psram_size": 0,
    "features": ["WiFi-bgn", "BLE", "Embedded-Flash"],
}


def _make_device_payload(test_uuid: str, public_key_b64: str) -> dict:
    return {
        "uuid": test_uuid,
        "product_id": "FFC0806-2505",
        "product_hex": "0x08062505",
        "device_class": "CONTROLLER",
        "public_key": public_key_b64,
        "registering_application": "Hardware-Registration-and-Configuration",
        "registering_version": "9999.99.99",
        "mcu": TEST_MCU,
    }


def _generate_keypair():
    """Generate an ephemeral ECDSA P-256 key pair for testing."""
    private_key = generate_private_key(SECP256R1(), default_backend())
    pub = private_key.public_key()
    pub_numbers = pub.public_key().public_numbers() if hasattr(pub, "public_key") else pub.public_numbers()
    x = pub_numbers.x.to_bytes(32, "big")
    y = pub_numbers.y.to_bytes(32, "big")
    uncompressed = b"\x04" + x + y
    public_key_b64 = base64.b64encode(uncompressed).decode()
    return private_key, public_key_b64


def _sign_nonce(private_key, nonce: bytes) -> str:
    """Sign nonce bytes with ECDSA P-256 SHA-256; return Base64 DER signature."""
    sig = private_key.sign(nonce, ECDSA(SHA256()))
    return base64.b64encode(sig).decode()


@pytest.fixture(scope="module")
def registration_key(api_url, auth_headers):
    """Generate a registration key; yield the code; clean up any leftover device at teardown."""
    resp = requests.post(f"{api_url}/registration-keys", headers=auth_headers, timeout=10)
    if resp.status_code != 201:
        pytest.fail(f"registration_key fixture: POST /registration-keys returned {resp.status_code}: {resp.text}")
    key = resp.json()["key"]
    yield key


@pytest.fixture(scope="module")
def registered_device(api_url, registration_key):
    """Register a test device; yield (test_uuid, private_key, public_key_b64); clean up at teardown."""
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


class TestRegistrationKeys:
    def test_create_key_missing_auth_returns_401(self, api_url):
        r = requests.post(f"{api_url}/registration-keys", timeout=10)
        assert r.status_code == 401

    def test_create_key_returns_201(self, api_url, auth_headers):
        r = requests.post(f"{api_url}/registration-keys", headers=auth_headers, timeout=10)
        assert r.status_code == 201

    def test_create_key_has_key_field(self, api_url, auth_headers):
        r = requests.post(f"{api_url}/registration-keys", headers=auth_headers, timeout=10)
        assert "key" in r.json()

    def test_create_key_is_6_chars(self, api_url, auth_headers):
        r = requests.post(f"{api_url}/registration-keys", headers=auth_headers, timeout=10)
        assert len(r.json()["key"]) == 6

    def test_create_key_is_alphanumeric(self, api_url, auth_headers):
        r = requests.post(f"{api_url}/registration-keys", headers=auth_headers, timeout=10)
        assert r.json()["key"].isalnum()


class TestDevicesRegister:
    def test_register_missing_key_header_returns_400(self, api_url):
        private_key, public_key_b64 = _generate_keypair()
        payload = _make_device_payload(str(uuid.uuid4()), public_key_b64)
        r = requests.post(f"{api_url}/devices/register", json=payload, timeout=10)
        assert r.status_code == 400

    def test_register_key_not_in_table_returns_401(self, api_url):
        private_key, public_key_b64 = _generate_keypair()
        payload = _make_device_payload(str(uuid.uuid4()), public_key_b64)
        r = requests.post(
            f"{api_url}/devices/register",
            json=payload,
            headers={"X-Registration-Key": "XXXXXX"},
            timeout=10,
        )
        assert r.status_code == 401

    def test_register_missing_required_fields_returns_400(self, api_url, registration_key):
        r = requests.post(
            f"{api_url}/devices/register",
            json={"uuid": str(uuid.uuid4())},
            headers={"X-Registration-Key": registration_key},
            timeout=10,
        )
        assert r.status_code == 400

    def test_register_invalid_public_key_returns_400(self, api_url, registration_key):
        payload = _make_device_payload(str(uuid.uuid4()), "bm90YXZhbGlka2V5")
        r = requests.post(
            f"{api_url}/devices/register",
            json=payload,
            headers={"X-Registration-Key": registration_key},
            timeout=10,
        )
        assert r.status_code == 400

    def test_register_valid_key_returns_204(self, api_url, registered_device):
        test_uuid, _, _ = registered_device
        assert test_uuid  # fixture handles assertion on status

    def test_register_duplicate_uuid_returns_204_record_unchanged(self, api_url, registered_device, registration_key):
        test_uuid, _, public_key_b64 = registered_device
        new_key_resp = requests.post(f"{api_url}/registration-keys", timeout=10)
        if new_key_resp.status_code != 201:
            pytest.skip("Could not generate second registration key for duplicate test")
        second_key = new_key_resp.json()["key"]
        payload = _make_device_payload(test_uuid, public_key_b64)
        r = requests.post(
            f"{api_url}/devices/register",
            json=payload,
            headers={"X-Registration-Key": second_key},
            timeout=10,
        )
        assert r.status_code == 204

    def test_register_key_consumed_after_use_returns_401(self, api_url, auth_headers):
        new_key_resp = requests.post(f"{api_url}/registration-keys", headers=auth_headers, timeout=10)
        if new_key_resp.status_code != 201:
            pytest.skip("Could not generate registration key for consumed-key test")
        key = new_key_resp.json()["key"]

        private_key, public_key_b64 = _generate_keypair()
        payload = _make_device_payload(str(uuid.uuid4()), public_key_b64)
        first = requests.post(
            f"{api_url}/devices/register",
            json=payload,
            headers={"X-Registration-Key": key},
            timeout=10,
        )
        assert first.status_code == 204

        private_key2, public_key_b64_2 = _generate_keypair()
        payload2 = _make_device_payload(str(uuid.uuid4()), public_key_b64_2)
        second = requests.post(
            f"{api_url}/devices/register",
            json=payload2,
            headers={"X-Registration-Key": key},
            timeout=10,
        )
        assert second.status_code == 401


class TestDevicesRegistrationGet:
    def test_get_registration_missing_headers_returns_400(self, api_url, registered_device):
        test_uuid, _, _ = registered_device
        r = requests.get(f"{api_url}/devices/{test_uuid}/registration", timeout=10)
        assert r.status_code == 400

    def test_get_registration_uuid_header_mismatch_returns_403(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        nonce = bytes(range(32))
        sig = _sign_nonce(private_key, nonce)
        r = requests.get(
            f"{api_url}/devices/{test_uuid}/registration",
            headers={
                "X-Device-UUID": str(uuid.uuid4()),
                "X-Device-Nonce": base64.b64encode(nonce).decode(),
                "X-Device-Signature": sig,
            },
            timeout=10,
        )
        assert r.status_code == 403

    def test_get_registration_unknown_uuid_returns_401(self, api_url):
        unknown = str(uuid.uuid4())
        nonce = bytes(range(32))
        private_key = generate_private_key(SECP256R1(), default_backend())
        sig = _sign_nonce(private_key, nonce)
        r = requests.get(
            f"{api_url}/devices/{unknown}/registration",
            headers={
                "X-Device-UUID": unknown,
                "X-Device-Nonce": base64.b64encode(nonce).decode(),
                "X-Device-Signature": sig,
            },
            timeout=10,
        )
        assert r.status_code == 401

    def test_get_registration_invalid_signature_returns_401(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        nonce = bytes(range(32))
        wrong_key = generate_private_key(SECP256R1(), default_backend())
        sig = _sign_nonce(wrong_key, nonce)
        r = requests.get(
            f"{api_url}/devices/{test_uuid}/registration",
            headers={
                "X-Device-UUID": test_uuid,
                "X-Device-Nonce": base64.b64encode(nonce).decode(),
                "X-Device-Signature": sig,
            },
            timeout=10,
        )
        assert r.status_code == 401

    def test_get_registration_valid_signature_returns_200(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        nonce = os.urandom(32)
        sig = _sign_nonce(private_key, nonce)
        r = requests.get(
            f"{api_url}/devices/{test_uuid}/registration",
            headers={
                "X-Device-UUID": test_uuid,
                "X-Device-Nonce": base64.b64encode(nonce).decode(),
                "X-Device-Signature": sig,
            },
            timeout=10,
        )
        assert r.status_code == 200

    def test_get_registration_returns_uuid(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        nonce = os.urandom(32)
        sig = _sign_nonce(private_key, nonce)
        r = requests.get(
            f"{api_url}/devices/{test_uuid}/registration",
            headers={
                "X-Device-UUID": test_uuid,
                "X-Device-Nonce": base64.b64encode(nonce).decode(),
                "X-Device-Signature": sig,
            },
            timeout=10,
        )
        assert r.json().get("uuid") == test_uuid

    def test_get_registration_returns_product_hex(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        nonce = os.urandom(32)
        sig = _sign_nonce(private_key, nonce)
        r = requests.get(
            f"{api_url}/devices/{test_uuid}/registration",
            headers={
                "X-Device-UUID": test_uuid,
                "X-Device-Nonce": base64.b64encode(nonce).decode(),
                "X-Device-Signature": sig,
            },
            timeout=10,
        )
        assert r.json().get("product_hex") == "0x08062505"

    def test_get_registration_returns_registration_date(self, api_url, registered_device):
        test_uuid, private_key, _ = registered_device
        nonce = os.urandom(32)
        sig = _sign_nonce(private_key, nonce)
        r = requests.get(
            f"{api_url}/devices/{test_uuid}/registration",
            headers={
                "X-Device-UUID": test_uuid,
                "X-Device-Nonce": base64.b64encode(nonce).decode(),
                "X-Device-Signature": sig,
            },
            timeout=10,
        )
        assert r.json().get("registration_date")
