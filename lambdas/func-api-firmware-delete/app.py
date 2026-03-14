from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import json
import boto3
import os
from boto3.dynamodb.conditions import Key

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

dynamodb = boto3.resource("dynamodb", endpoint_url=os.environ.get("DYNAMODB_ENDPOINT"))
s3 = boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT"))

TABLE_NAME = os.environ["DYNAMODB_FIRMWARE_TABLE_NAME"]
BUCKET_NAME = os.environ["S3_FIRMWARE_BUCKET_NAME"]

firmware_table = dynamodb.Table(TABLE_NAME)

PROCESSED_PREFIX = "processed/"
ERROR_PREFIX = "errors/"

# These states indicate the S3 file has already been removed
ALREADY_REMOVED_STATES = {"DELETED", "REVOKED"}


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, indent=4, default=str),
    }


def lambda_handler(event, context):
    try:
        path_params = event.get("pathParameters") or {}
        zip_name = path_params.get("zip_name")

        logger.debug(f"DELETE firmware zip_name='{zip_name}'")

        # Query GSI 2 by zip_name (UUID) — the unique identifier for a specific build.
        response = firmware_table.query(
            IndexName="zip_name-index",
            KeyConditionExpression=Key("zip_name").eq(zip_name)
        )
        items = response.get("Items", [])
        if not items:
            return _response(404, {"message": f"Firmware not found: {zip_name}"})

        item = items[0]
        release_status = item.get("release_status")

        if release_status in ALREADY_REMOVED_STATES:
            return _response(409, {
                "message": f"Firmware is already in state '{release_status}'; the S3 file has been removed"
            })

        prefix = ERROR_PREFIX if release_status == "ERROR" else PROCESSED_PREFIX
        s3_key = f"{prefix}{zip_name}"

        logger.debug(f"Deleting s3://{BUCKET_NAME}/{s3_key} (status: '{release_status}')")

        s3.delete_object(Bucket=BUCKET_NAME, Key=s3_key)

        # DynamoDB status update (DELETED or REVOKED) is handled asynchronously
        # by func-s3-firmware-deleted, which is triggered by the S3 delete event above.
        return _response(202, {"message": "Deletion initiated"})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
