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
  ETag                 SHA-256 hex of the plaintext backup content (from /backup.etag
                         on the device); stored as S3 object metadata and returned
                         by GET so the controller can restore /backup.etag after a restore
  If-None-Match        Plaintext SHA-256 ETag of the backup the client believes is
                         already stored (as returned by a previous POST or GET).
                         Compared against the stored S3 metadata ETag. Only evaluated
                         when the ETag request header is also present; 304 returned if
                         they match. Skipped if ETag header is absent.

Responses:
  200  Backup stored successfully
  304  Backup unchanged (plaintext ETag match); only returned when both ETag and
         If-None-Match headers are present
  400  Missing/invalid headers or body too large
  401  Device not registered or signature invalid
  403  UUID mismatch
  413  Payload too large (> 512 KB)
  500  Internal server error
"""

import base64
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

        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        etag = headers.get("etag", "").strip().strip('"')
        if_none_match = headers.get("if-none-match", "").strip().strip('"')

        s3_key = path_uuid

        # 304 short-circuit: client asserts current content matches stored content
        if etag and if_none_match and etag == if_none_match:
            return {
                "statusCode": 304,
                "headers": {
                    "ETag": f'"{etag}"',
                    "Content-Type": "application/json",
                },
                "body": "",
            }

        # Store backup in S3
        try:
            put_kwargs = {
                "Bucket": BACKUP_BUCKET_NAME,
                "Key": s3_key,
                "Body": body_bytes,
                "ContentType": "application/octet-stream",
            }
            if etag:
                put_kwargs["Metadata"] = {"etag": etag}
            s3.put_object(**put_kwargs)
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

        response_headers = {"Content-Type": "application/json"}
        if etag:
            response_headers["ETag"] = f'"{etag}"'

        return {
            "statusCode": 200,
            "headers": response_headers,
            "body": json.dumps({"message": "Backup stored", "last_backup_date": now_iso}),
        }

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
