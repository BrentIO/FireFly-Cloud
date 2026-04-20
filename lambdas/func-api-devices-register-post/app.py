"""
POST /devices/register — register a device with FireFly-Cloud.

Validates the X-Registration-Key header against the registration_keys table,
writes the device record to the devices table, and deletes the consumed key.
Returns 204 on success. If the device UUID already exists, returns 204 immediately
without modifying the existing record.

Required headers:
  X-Registration-Key   6-character one-time registration key

Body fields (required): uuid, product_id, product_hex, device_class, public_key,
                        registering_application, registering_version, mcu
Body fields (optional): network (array of {interface, mac_address} objects)
"""

import json
import os
import re
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

from shared.app_config import get_appconfig
from shared.logging_config import configure_logger

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

dynamodb = boto3.resource("dynamodb")
DEVICES_TABLE_NAME = os.environ["DYNAMODB_DEVICES_TABLE_NAME"]
REGISTRATION_KEYS_TABLE_NAME = os.environ["DYNAMODB_REGISTRATION_KEYS_TABLE_NAME"]

devices_table = dynamodb.Table(DEVICES_TABLE_NAME)
registration_keys_table = dynamodb.Table(REGISTRATION_KEYS_TABLE_NAME)

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
PRODUCT_HEX_RE = re.compile(r"^0x[0-9A-Fa-f]{8}$")
REQUIRED_BODY_FIELDS = [
    "uuid", "product_id", "product_hex", "device_class",
    "public_key", "registering_application", "registering_version", "mcu",
]


def _response(status_code, body=None):
    resp = {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
    }
    resp["body"] = json.dumps(body, indent=4, default=str) if body is not None else ""
    return resp


def lambda_handler(event, context):
    try:
        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        registration_key = headers.get("x-registration-key", "").strip()

        if not registration_key or len(registration_key) != 6:
            return _response(400, {"message": "X-Registration-Key header is required and must be 6 characters"})

        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _response(400, {"message": "Invalid JSON body"})

        for field in REQUIRED_BODY_FIELDS:
            if not body.get(field):
                return _response(400, {"message": f"{field} is required"})

        uuid = body["uuid"].strip()
        if not UUID_RE.match(uuid):
            return _response(400, {"message": "uuid must be a valid UUID"})

        product_hex = body["product_hex"].strip()
        if not PRODUCT_HEX_RE.match(product_hex):
            return _response(400, {"message": "product_hex must match 0xXXXXXXXX"})

        public_key = body["public_key"]
        try:
            import base64
            decoded = base64.b64decode(public_key, validate=True)
            if len(decoded) != 65 or decoded[0] != 0x04:
                return _response(400, {"message": "public_key must be a Base64-encoded uncompressed P-256 point (65 bytes, prefix 0x04)"})
        except Exception:
            return _response(400, {"message": "public_key must be valid Base64"})

        # Validate registration key
        key_item = registration_keys_table.get_item(Key={"key": registration_key}).get("Item")
        if not key_item:
            logger.warning("Registration key not found: %s", registration_key)
            return _response(401, {"message": "Invalid or expired registration key"})

        # If device already registered, return 204 immediately (idempotent)
        existing = devices_table.get_item(Key={"uuid": uuid}).get("Item")
        if existing:
            logger.info("Device already registered, returning 204: %s", uuid)
            return _response(204)

        now = datetime.now(timezone.utc).isoformat()

        item = {
            "uuid": uuid,
            "product_id": body["product_id"],
            "product_hex": product_hex,
            "device_class": body["device_class"],
            "public_key": public_key,
            "registration_date": now,
            "registering_application": body["registering_application"],
            "registering_version": body["registering_version"],
            "mcu": body["mcu"],
        }

        if body.get("network") is not None:
            item["network"] = body["network"]

        if body.get("partitions") is not None:
            item["partitions"] = body["partitions"]

        devices_table.put_item(
            Item=item,
            ConditionExpression=Attr("uuid").not_exists(),
        )

        registration_keys_table.delete_item(Key={"key": registration_key})

        logger.info("Device registered: %s product_hex=%s", uuid, product_hex)
        return _response(204)

    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        logger.info("Device already registered (race condition), returning 204: %s", body.get("uuid"))
        return _response(204)

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
