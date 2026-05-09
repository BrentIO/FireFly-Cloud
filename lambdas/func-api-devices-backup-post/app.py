"""
POST /devices/{uuid}/backup — store an encrypted configuration backup.

The request body must be the raw FFCE-format encrypted binary (max 512 KB).
Authentication uses the shared device_auth module, which verifies the ECDSA
P-256 signature over SHA-256(nonce||timestamp) and enforces a ±500 ms
timestamp window.

Required headers:
  Content-Type         application/octet-stream
  X-Device-UUID        Must match the {uuid} path parameter
  X-Device-Nonce       Base64-encoded 32-byte random nonce
  X-Device-Timestamp   ISO 8601 UTC timestamp (e.g. "2025-05-09T12:00:00Z")
  X-Device-Signature   Base64-encoded DER ECDSA P-256 signature over
                         SHA-256(nonce_bytes || timestamp_ascii_bytes)

Optional headers:
  If-None-Match        ETag of existing backup; returns 304 if unchanged

Responses:
  200  Backup stored successfully
  304  Backup unchanged (ETag match)
  400  Missing/invalid headers or body too large
  401  Device not registered or signature invalid
  403  UUID mismatch
  413  Payload too large (> 512 KB)
  500  Internal server error
"""

import base64
import hashlib
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

_MAX_BODY_BYTES = 512 * 1024  # 512 KB


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

        # Decode body
        raw_body = event.get("body") or ""
        is_base64 = event.get("isBase64Encoded", False)

        if is_base64:
            try:
                body_bytes = base64.b64decode(raw_body)
            except Exception:
                return _response(400, {"message": "Invalid base64-encoded body"})
        else:
            body_bytes = raw_body.encode("latin-1") if isinstance(raw_body, str) else raw_body

        if len(body_bytes) == 0:
            return _response(400, {"message": "Request body is required"})

        if len(body_bytes) > _MAX_BODY_BYTES:
            return _response(413, {"message": f"Payload exceeds maximum size of {_MAX_BODY_BYTES // 1024} KB"})

        # Validate FFCE magic header
        if len(body_bytes) < 4 or body_bytes[:4] != b"FFCE":
            return _response(400, {"message": "Body does not appear to be a valid FFCE backup"})

        # Compute ETag as MD5 of the body (matches S3 ETag for single-part uploads)
        etag = hashlib.md5(body_bytes).hexdigest()

        # Check If-None-Match header for 304 short-circuit
        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        if_none_match = headers.get("if-none-match", "").strip().strip('"')
        if if_none_match and if_none_match == etag:
            return {
                "statusCode": 304,
                "headers": {
                    "ETag": f'"{etag}"',
                    "Content-Type": "application/json",
                },
                "body": "",
            }

        s3_key = f"{path_uuid}/backup.ffce"

        # Also check against the existing S3 object ETag to avoid redundant writes
        if not if_none_match:
            try:
                head = s3.head_object(Bucket=BACKUP_BUCKET_NAME, Key=s3_key)
                existing_etag = head.get("ETag", "").strip('"')
                if existing_etag and existing_etag == etag:
                    return {
                        "statusCode": 304,
                        "headers": {
                            "ETag": f'"{etag}"',
                            "Content-Type": "application/json",
                        },
                        "body": "",
                    }
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "404":
                    logger.warning("head_object failed for %s: %s", path_uuid, exc)

        # Store backup in S3
        try:
            s3.put_object(
                Bucket=BACKUP_BUCKET_NAME,
                Key=s3_key,
                Body=body_bytes,
                ContentType="application/octet-stream",
            )
        except ClientError:
            logger.exception("Failed to store backup for device %s", path_uuid)
            return _response(500, {"message": "Internal server error"})

        # Update last_backup_date in DynamoDB
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            devices_table.update_item(
                Key={"uuid": path_uuid},
                UpdateExpression="SET last_backup_date = :d",
                ExpressionAttributeValues={":d": now_iso},
            )
        except ClientError:
            logger.exception("Failed to update last_backup_date for device %s", path_uuid)
            # Non-fatal: backup was stored; just log and continue

        return {
            "statusCode": 200,
            "headers": {
                "ETag": f'"{etag}"',
                "Content-Type": "application/json",
            },
            "body": json.dumps({"message": "Backup stored", "last_backup_date": now_iso}),
        }

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
