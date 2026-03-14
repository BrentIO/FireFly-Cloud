from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import boto3
import os
import time
from urllib.parse import unquote_plus
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

dynamodb = boto3.resource("dynamodb", endpoint_url=os.environ.get("DYNAMODB_ENDPOINT"))

TABLE_NAME = os.environ["DYNAMODB_FIRMWARE_TABLE_NAME"]
firmware_table = dynamodb.Table(TABLE_NAME)

TTL_DAYS = 10
TTL_SECONDS = TTL_DAYS * 24 * 3600

def mark_deleted_by_zip(filename: str) -> None:
    """
    Find all items with this zip_name and mark them deleted with a TTL.
    We scan because the primary key is (product_id, version), not zip_name.
    """

    expires_at = int(time.time()) + TTL_SECONDS

    # Small table size (<1000 items) makes a scan acceptable here.
    response = firmware_table.scan(
        FilterExpression=Attr("zip_name").eq(filename)
    )

    items = response.get("Items", [])

    if response.get("Count") == 0:
        raise Exception(f"DynamoDB did not return any objects for filename {filename}.")

    for item in items:
        product_id = item.get("product_id")
        version = item.get("version")

        try:
            firmware_table.update_item(
                Key={
                    "product_id": product_id,
                    "version": version,
                },
                UpdateExpression="SET #ttl = :ttl, release_status = :rs",
                ConditionExpression="attribute_exists(product_id) AND attribute_exists(version)",
                ExpressionAttributeNames={
                    "#ttl": "ttl",
                },
                ExpressionAttributeValues={
                    ":ttl": expires_at,
                    ":rs": "DELETED",
                },
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise Exception(f"Failed to update DynamoDB for {filename}.")
                # Item disappeared or never existed with this key
                continue
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