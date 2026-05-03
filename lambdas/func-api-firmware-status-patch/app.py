from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
from decimal import Decimal
import io
import json
import time
import zipfile
import boto3
import os
from boto3.dynamodb.conditions import Attr, Key

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

dynamodb = boto3.resource("dynamodb", endpoint_url=os.environ.get("DYNAMODB_ENDPOINT"))
s3 = boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT"))

TABLE_NAME = os.environ["DYNAMODB_FIRMWARE_TABLE_NAME"]
S3_FIRMWARE_PRIVATE_BUCKET_NAME = os.environ["S3_FIRMWARE_PRIVATE_BUCKET_NAME"]
S3_FIRMWARE_PUBLIC_BUCKET_NAME = os.environ["S3_FIRMWARE_PUBLIC_BUCKET_NAME"]

firmware_table = dynamodb.Table(TABLE_NAME)

VALID_TRANSITIONS = {
    "READY_TO_TEST": ["TESTING"],
    "TESTING": ["READY_TO_TEST", "RELEASED"],
    "RELEASED": ["REVOKED"],
}

PROCESSED_PREFIX = "processed/"
EXCLUDE_FROM_OTA = {"config.bin", "manifest.json"}

TTL_DAYS = 10
TTL_SECONDS = TTL_DAYS * 24 * 3600


def _json_default(obj):
    if isinstance(obj, Decimal):
        n = int(obj)
        return n if n == obj else float(obj)
    return str(obj)


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, indent=4, default=_json_default),
    }


def _publish_to_public(item, zip_name):
    """Extract firmware files from the private ZIP and upload to the public bucket."""
    device_class = item.get("class", "").lower()
    product_hex = item.get("product_hex", "").lower()
    version = item["version"]
    zip_key = f"{PROCESSED_PREFIX}{zip_name}"

    logger.debug(f"Fetching ZIP s3://{S3_FIRMWARE_PRIVATE_BUCKET_NAME}/{zip_key}")
    zip_obj = s3.get_object(Bucket=S3_FIRMWARE_PRIVATE_BUCKET_NAME, Key=zip_key)
    zip_bytes = zip_obj["Body"].read()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if name in EXCLUDE_FROM_OTA:
                logger.debug(f"Skipping excluded file: {name}")
                continue
            dest_key = f"{device_class}/{product_hex}/{version}/{name}"
            data = zf.read(name)
            s3.put_object(Bucket=S3_FIRMWARE_PUBLIC_BUCKET_NAME, Key=dest_key, Body=data)
            logger.debug(f"Published {name} to s3://{S3_FIRMWARE_PUBLIC_BUCKET_NAME}/{dest_key}")


def _revoke_from_public(item):
    """Move public firmware files to the revoked/ prefix."""
    device_class = item.get("class", "").lower()
    product_hex = item.get("product_hex", "").lower()
    version = item["version"]
    prefix = f"{device_class}/{product_hex}/{version}/"
    revoked_prefix = f"revoked/{device_class}/{product_hex}/{version}/"

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_FIRMWARE_PUBLIC_BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []):
            src_key = obj["Key"]
            filename = os.path.basename(src_key)
            dest_key = f"{revoked_prefix}{filename}"
            s3.copy_object(
                Bucket=S3_FIRMWARE_PUBLIC_BUCKET_NAME,
                CopySource={"Bucket": S3_FIRMWARE_PUBLIC_BUCKET_NAME, "Key": src_key},
                Key=dest_key,
            )
            s3.delete_object(Bucket=S3_FIRMWARE_PUBLIC_BUCKET_NAME, Key=src_key)
            logger.debug(f"Moved s3://{S3_FIRMWARE_PUBLIC_BUCKET_NAME}/{src_key} to {dest_key}")


def lambda_handler(event, context):
    try:
        path_params = event.get("pathParameters") or {}
        zip_name = path_params.get("zip_name")

        body = json.loads(event.get("body") or "{}")
        new_status = body.get("release_status")

        if not new_status:
            return _response(400, {"message": "Missing required field: release_status"})

        logger.debug(f"PATCH status for zip_name='{zip_name}' new_status='{new_status}'")

        # Query GSI 2 by zip_name (UUID) — the unique identifier for a specific build.
        response = firmware_table.query(
            IndexName="zip_name-index",
            KeyConditionExpression=Key("zip_name").eq(zip_name)
        )
        items = response.get("Items", [])
        if not items:
            return _response(404, {"message": f"Firmware not found: {zip_name}"})

        pk = items[0]["pk"]
        version = items[0]["version"]

        # Re-read from the main table with strong consistency — GSI reads are
        # eventually consistent and can return a stale status immediately after
        # a transition, causing a spurious 422 on the next PATCH.
        consistent = firmware_table.get_item(
            Key={"pk": pk, "version": version},
            ConsistentRead=True
        ).get("Item")
        item = consistent if consistent else items[0]
        current_status = item.get("release_status")
        allowed = VALID_TRANSITIONS.get(current_status, [])

        if new_status not in allowed:
            return _response(422, {
                "message": f"Cannot transition from '{current_status}' to '{new_status}'",
                "current_status": current_status,
                "allowed_transitions": allowed,
            })

        # Perform S3 side effects before updating DynamoDB so the status only
        # advances if the S3 operation succeeds.
        if new_status == "RELEASED":
            _publish_to_public(item, zip_name)

        if new_status == "REVOKED":
            _revoke_from_public(item)

        now = int(time.time())
        history_entry = [{"status": new_status, "timestamp": now}]

        update_expression = (
            "SET release_status = :rs, "
            "status_history = list_append(if_not_exists(status_history, :empty), :entry)"
        )
        expression_values = {
            ":rs": new_status,
            ":empty": [],
            ":entry": history_entry,
        }

        # Set a DynamoDB TTL when revoking so the record is auto-purged.
        if new_status == "REVOKED":
            expires_at = now + TTL_SECONDS
            update_expression += ", #ttl = :ttl"
            expression_values[":ttl"] = expires_at

        kwargs = {
            "Key": {"pk": pk, "version": version},
            "UpdateExpression": update_expression,
            "ExpressionAttributeValues": expression_values,
        }
        if new_status == "REVOKED":
            kwargs["ExpressionAttributeNames"] = {"#ttl": "ttl"}

        firmware_table.update_item(**kwargs)

        logger.debug(f"Transitioned zip_name='{zip_name}' from '{current_status}' to '{new_status}'")

        item["release_status"] = new_status
        item.setdefault("status_history", [])
        item["status_history"].append({"status": new_status, "timestamp": now})
        item.pop("pk", None)
        return _response(200, item)

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
