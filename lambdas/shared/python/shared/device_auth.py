"""
Shared device authentication helper.

Validates the four device-identity headers that all device-initiated cloud
requests must carry:

  X-Device-UUID        UUID of the calling device (must match path parameter)
  X-Device-Nonce       Base64-encoded 32-byte random nonce
  X-Device-Timestamp   ISO 8601 UTC timestamp string (e.g. "2025-05-09T12:00:00Z")
  X-Device-Signature   Base64-encoded DER ECDSA P-256 signature over
                         SHA-256(nonce_bytes || timestamp_ascii_bytes)

The timestamp must be within ±10 seconds of the server's current UTC clock.
The signature is verified against the device's registered public key.
"""

import base64
import logging
from datetime import datetime, timezone, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA, SECP256R1, EllipticCurvePublicNumbers
from cryptography.hazmat.primitives.hashes import SHA256

logger = logging.getLogger(__name__)

_TIMESTAMP_WINDOW = timedelta(seconds=10)


class DeviceAuthError(Exception):
    """Raised when device authentication fails."""
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.status_code = status_code


def _load_public_key(public_key_b64: str):
    """Load an uncompressed P-256 public key from Base64."""
    raw = base64.b64decode(public_key_b64)
    if len(raw) != 65 or raw[0] != 0x04:
        raise DeviceAuthError("Stored public key is not a valid 65-byte uncompressed P-256 point", 500)
    x = int.from_bytes(raw[1:33], "big")
    y = int.from_bytes(raw[33:65], "big")
    pub_numbers = EllipticCurvePublicNumbers(x=x, y=y, curve=SECP256R1())
    return pub_numbers.public_key(default_backend())


def verify_device_request(event: dict, expected_uuid: str, device_item: dict) -> None:
    """
    Validate device authentication headers from an API Gateway v2 event.

    Parameters
    ----------
    event          : Lambda event dict (API Gateway HTTP API payload v2)
    expected_uuid  : UUID from the path parameter (used to cross-check header)
    device_item    : DynamoDB item for this device (must contain 'public_key')

    Raises
    ------
    DeviceAuthError with an appropriate status_code on any validation failure.
    """
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    header_uuid   = headers.get("x-device-uuid", "").strip()
    nonce_b64     = headers.get("x-device-nonce", "").strip()
    timestamp_str = headers.get("x-device-timestamp", "").strip()
    sig_b64       = headers.get("x-device-signature", "").strip()

    if not header_uuid or not nonce_b64 or not timestamp_str or not sig_b64:
        raise DeviceAuthError(
            "X-Device-UUID, X-Device-Nonce, X-Device-Timestamp, and "
            "X-Device-Signature headers are required",
            400,
        )

    if header_uuid != expected_uuid:
        raise DeviceAuthError("X-Device-UUID header does not match path parameter", 403)

    # Decode nonce and signature
    try:
        nonce_bytes = base64.b64decode(nonce_b64, validate=True)
        sig_der     = base64.b64decode(sig_b64,   validate=True)
    except Exception:
        raise DeviceAuthError("X-Device-Nonce and X-Device-Signature must be valid Base64", 400)

    if len(nonce_bytes) != 32:
        raise DeviceAuthError("X-Device-Nonce must be 32 bytes", 400)

    # Parse and validate timestamp window
    try:
        device_time = datetime.fromisoformat(timestamp_str.rstrip("Z")).replace(tzinfo=timezone.utc)
    except ValueError:
        raise DeviceAuthError("X-Device-Timestamp must be ISO 8601 UTC (e.g. 2025-05-09T12:00:00Z)", 400)

    server_time = datetime.now(timezone.utc)
    delta = abs(server_time - device_time)
    if delta > _TIMESTAMP_WINDOW:
        logger.warning(
            "Timestamp out of window for device %s: delta=%s",
            expected_uuid,
            delta,
        )
        raise DeviceAuthError("X-Device-Timestamp is outside the acceptance window", 401)

    # Verify signature over nonce_bytes || timestamp_ascii_bytes
    # ECDSA(SHA256()) hashes internally; do not pre-hash
    ts_bytes = timestamp_str.encode("ascii")
    try:
        pub_key = _load_public_key(device_item["public_key"])
        pub_key.verify(sig_der, nonce_bytes + ts_bytes, ECDSA(SHA256()))
    except InvalidSignature:
        logger.warning("Invalid signature for device %s", expected_uuid)
        raise DeviceAuthError("Signature verification failed", 401)
    except DeviceAuthError:
        raise
    except Exception as exc:
        logger.exception("Error verifying signature for device %s", expected_uuid)
        raise DeviceAuthError("Signature verification failed", 401) from exc
