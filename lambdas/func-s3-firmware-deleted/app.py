import boto3
import os
import time
from urllib.parse import unquote_plus
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource("dynamodb")

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

    for item in items:
        product_id = item.get("product_id")
        version = item.get("version")

        if not product_id or not version:
            # Shouldn't happen, but don't blow up the whole batch
            continue

        try:
            firmware_table.update_item(
                Key={
                    "product_id": product_id,
                    "version": version,
                },
                UpdateExpression="SET deleted = :d, ttl = :ttl",
                ConditionExpression="attribute_exists(product_id) AND attribute_exists(version)",
                ExpressionAttributeValues={
                    ":d": True,
                    ":ttl": expires_at,
                },
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # Item disappeared or never existed with this key; ignore
                continue
            else:
                raise


def lambda_handler(event, context):
    for record in event.get("Records", []):
        key = unquote_plus(record["s3"]["object"]["key"])
        filename = os.path.basename(key)

        # Ignore non-zip deletions
        if not filename.endswith(".zip"):
            continue

        # We only care about processed/ and errors/ prefixes,
        # but behavior is the same: mark matching records deleted.
        if key.startswith("processed/") or key.startswith("errors/"):
            mark_deleted_by_zip(filename)
