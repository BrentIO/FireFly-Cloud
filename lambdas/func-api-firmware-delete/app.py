from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import json
import boto3
import os

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
        product_id = path_params.get("product_id")
        version = path_params.get("version")

        logger.debug(f"DELETE firmware product_id='{product_id}' version='{version}'")

        response = firmware_table.get_item(
            Key={"product_id": product_id, "version": version}
        )
        item = response.get("Item")
        if not item:
            return _response(404, {"message": f"Firmware not found: {product_id}/{version}"})

        release_status = item.get("release_status")

        if release_status in ALREADY_REMOVED_STATES:
            return _response(409, {
                "message": f"Firmware is already in state '{release_status}'; the S3 file has been removed"
            })

        zip_name = item.get("zip_name")
        prefix = ERROR_PREFIX if release_status == "ERROR" else PROCESSED_PREFIX
        s3_key = f"{prefix}{zip_name}"

        logger.debug(f"Deleting s3://{BUCKET_NAME}/{s3_key} for product_id='{product_id}' version='{version}' (status: '{release_status}')")

        s3.delete_object(Bucket=BUCKET_NAME, Key=s3_key)

        # DynamoDB status update (DELETED or REVOKED) is handled asynchronously
        # by func-s3-firmware-deleted, which is triggered by the S3 delete event above.
        return _response(202, {"message": "Deletion initiated"})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
