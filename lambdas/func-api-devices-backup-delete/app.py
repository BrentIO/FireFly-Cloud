"""
DELETE /devices/{uuid}/backup — remove the stored configuration backup.

Authentication uses the shared device_auth module, which verifies the ECDSA
P-256 signature over SHA-256(nonce||timestamp) and enforces a ±500 ms
timestamp window.

Required headers:
  X-Device-UUID        Must match the {uuid} path parameter
  X-Device-Nonce       Base64-encoded 32-byte random nonce
  X-Device-Timestamp   ISO 8601 UTC timestamp (e.g. "2025-05-09T12:00:00Z")
  X-Device-Signature   Base64-encoded DER ECDSA P-256 signature over
                         SHA-256(nonce_bytes || timestamp_ascii_bytes)

Responses:
  200  Backup deleted (or did not exist)
  400  Missing/invalid headers
  401  Device not registered or signature invalid
  403  UUID mismatch
  500  Internal server error
"""

import json
import os

import boto3
from botocore.exceptions import ClientError

from shared.app_config import get_appconfig
from shared.device_auth import DeviceAuthError, verify_device_request
from shared.logging_config import configure_logger

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

DEVICES_TABLE_NAME = os.environ["DYNAMODB_DEVICES_TABLE_NAME"]
BACKUP_BUCKET_NAME = os.environ["S3_BACKUP_BUCKET_NAME"]

devices_table = dynamodb.Table(DEVICES_TABLE_NAME)


def _response(status_code, body=None):
    resp = {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
    }
    resp["body"] = json.dumps(body, indent=4, default=str) if body is not None else ""
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

        s3_key = f"{path_uuid}/backup.ffce"

        # Delete from S3 (idempotent — succeeds even if key does not exist)
        try:
            s3.delete_object(Bucket=BACKUP_BUCKET_NAME, Key=s3_key)
        except ClientError:
            logger.exception("Failed to delete backup for device %s", path_uuid)
            return _response(500, {"message": "Internal server error"})

        # Clear last_backup_date in DynamoDB
        try:
            devices_table.update_item(
                Key={"uuid": path_uuid},
                UpdateExpression="REMOVE last_backup_date",
            )
        except ClientError:
            logger.exception("Failed to clear last_backup_date for device %s", path_uuid)
            # Non-fatal: object already deleted; log and continue

        return _response(200, {"message": "Backup deleted"})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
