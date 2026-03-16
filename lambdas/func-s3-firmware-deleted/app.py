from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import boto3
import os
import time
from urllib.parse import unquote_plus
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr, Key

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

dynamodb = boto3.resource("dynamodb", endpoint_url=os.environ.get("DYNAMODB_ENDPOINT"))

TABLE_NAME = os.environ["DYNAMODB_FIRMWARE_TABLE_NAME"]
firmware_table = dynamodb.Table(TABLE_NAME)

TTL_DAYS = 10
TTL_SECONDS = TTL_DAYS * 24 * 3600

def mark_deleted_by_zip(filename: str) -> None:
    """
    Find the item with this zip_name via GSI and mark it deleted with a TTL.
    """

    expires_at = int(time.time()) + TTL_SECONDS

    response = firmware_table.query(
        IndexName="zip_name-index",
        KeyConditionExpression=Key("zip_name").eq(filename)
    )

    items = response.get("Items", [])

    if not items:
        raise Exception(f"DynamoDB did not return any objects for filename {filename}.")

    for item in items:
        pk = item.get("pk")
        version = item.get("version")
        current_status = item.get("release_status")

        # RELEASED and REVOKED records are managed by func-api-firmware-status-patch.
        # Deletions of private bucket files for these statuses occur during normal
        # lifecycle expiry and should not alter the DynamoDB record.
        # ERROR records are transitioned to DELETED synchronously by func-api-firmware-delete;
        # the S3 event fires after that update, so skip them here to avoid a redundant write.
        # DELETED records have already been processed.
        if current_status in {"RELEASED", "REVOKED", "ERROR", "DELETED"}:
            logger.debug(f"Skipping update for pk='{pk}' version='{version}' (status: '{current_status}')")
            continue

        new_status = "DELETED"
        logger.debug(f"Transitioning pk='{pk}' version='{version}' from '{current_status}' to '{new_status}'")

        try:
            firmware_table.update_item(
                Key={
                    "pk": pk,
                    "version": version,
                },
                UpdateExpression="SET #ttl = :ttl, release_status = :rs",
                ConditionExpression="attribute_exists(pk) AND attribute_exists(version)",
                ExpressionAttributeNames={
                    "#ttl": "ttl",
                },
                ExpressionAttributeValues={
                    ":ttl": expires_at,
                    ":rs": new_status,
                },
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise Exception(f"Failed to update DynamoDB for {filename}.")
            else:
                raise


def lambda_handler(event, context):

    try:
        for record in event.get("Records", []):
            key = unquote_plus(record["s3"]["object"]["key"])
            logger.debug(f"Processing key '{key}'")
            filename = os.path.basename(key)

            # Ignore non-zip deletions
            if not filename.endswith(".zip"):
                logger.warning(f"Filename '{filename}' does not end with .zip")
                continue

            # We only care about processed/ and errors/ prefixes,
            # but behavior is the same: mark matching records deleted.
            if key.startswith("processed/") or key.startswith("errors/"):
                mark_deleted_by_zip(filename)

    except Exception:
        logger.exception("Unhandled exception")
        raise