"""
GET /devices/{uuid}/registration — verify device registration status.

Authenticates the request using the shared device_auth module, which verifies
the ECDSA P-256 signature over SHA-256(nonce||timestamp) and enforces a ±10 s
timestamp window.

Required headers:
  X-Device-UUID        Must match the {uuid} path parameter
  X-Device-Nonce       Base64-encoded 32-byte random nonce
  X-Device-Timestamp   ISO 8601 UTC timestamp (e.g. "2025-05-09T12:00:00Z")
  X-Device-Signature   Base64-encoded DER ECDSA P-256 signature over
                         SHA-256(nonce_bytes || timestamp_ascii_bytes)
"""

import json
import os

import boto3

from shared.app_config import get_appconfig
from shared.device_auth import DeviceAuthError, verify_device_request
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
    resp["body"] = json.dumps(body, default=str) if body is not None else ""
    return resp


def lambda_handler(event, context):
    try:
        path_uuid = (event.get("pathParameters") or {}).get("uuid", "").strip()

        item = devices_table.get_item(Key={"uuid": path_uuid}).get("Item")
        if not item:
            return _response(401, {"message": "Device not registered"})

        try:
            verify_device_request(event, path_uuid, item)
        except DeviceAuthError as exc:
            return _response(exc.status_code, {"message": str(exc)})

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
