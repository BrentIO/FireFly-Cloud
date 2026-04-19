"""
GET /devices/{uuid}/registration — verify device registration status.

Authenticates the request by verifying an ECDSA P-256 signature over a
caller-supplied nonce using the public key stored at registration time.

Required headers:
  X-Device-UUID        Must match the {uuid} path parameter
  X-Device-Nonce       Base64-encoded 32-byte random nonce
  X-Device-Signature   Base64-encoded DER-format ECDSA P-256 signature over the nonce bytes
"""

import base64
import json
import os

import boto3
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDSA,
    EllipticCurvePublicKey,
    SECP256R1,
)
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from shared.app_config import get_appconfig
from shared.logging_config import configure_logger

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

dynamodb = boto3.resource("dynamodb")
DEVICES_TABLE_NAME = os.environ["DYNAMODB_DEVICES_TABLE_NAME"]
devices_table = dynamodb.Table(DEVICES_TABLE_NAME)


def _response(status_code, body=None):
    resp = {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
    }
    resp["body"] = json.dumps(body, indent=4, default=str) if body is not None else ""
    return resp


def _load_public_key(public_key_b64: str) -> EllipticCurvePublicKey:
    raw = base64.b64decode(public_key_b64)
    if len(raw) != 65 or raw[0] != 0x04:
        raise ValueError("Expected 65-byte uncompressed P-256 point")
    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicNumbers, SECP256R1
    x = int.from_bytes(raw[1:33], "big")
    y = int.from_bytes(raw[33:65], "big")
    pub_numbers = EllipticCurvePublicNumbers(x=x, y=y, curve=SECP256R1())
    return pub_numbers.public_key(default_backend())


def lambda_handler(event, context):
    try:
        path_uuid = (event.get("pathParameters") or {}).get("uuid", "").strip()
        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

        header_uuid = headers.get("x-device-uuid", "").strip()
        nonce_b64 = headers.get("x-device-nonce", "").strip()
        signature_b64 = headers.get("x-device-signature", "").strip()

        if not header_uuid or not nonce_b64 or not signature_b64:
            return _response(400, {"message": "X-Device-UUID, X-Device-Nonce, and X-Device-Signature headers are required"})

        if header_uuid != path_uuid:
            return _response(403, {"message": "X-Device-UUID header does not match path parameter"})

        item = devices_table.get_item(Key={"uuid": path_uuid}).get("Item")
        if not item:
            return _response(401, {"message": "Device not registered"})

        try:
            nonce = base64.b64decode(nonce_b64, validate=True)
            signature_der = base64.b64decode(signature_b64, validate=True)
        except Exception:
            return _response(400, {"message": "X-Device-Nonce and X-Device-Signature must be valid Base64"})

        if len(nonce) != 32:
            return _response(400, {"message": "X-Device-Nonce must be 32 bytes"})

        try:
            pub_key = _load_public_key(item["public_key"])
            pub_key.verify(signature_der, nonce, ECDSA(SHA256()))
        except InvalidSignature:
            logger.warning("Invalid signature for device: %s", path_uuid)
            return _response(401, {"message": "Signature verification failed"})
        except Exception:
            logger.exception("Public key load or verify error for device: %s", path_uuid)
            return _response(401, {"message": "Signature verification failed"})

        return _response(200, {
            "uuid": item["uuid"],
            "product_id": item.get("product_id"),
            "product_hex": item.get("product_hex"),
            "device_class": item.get("device_class"),
            "registration_date": item.get("registration_date"),
            "registering_application": item.get("registering_application"),
            "registering_version": item.get("registering_version"),
        })

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
