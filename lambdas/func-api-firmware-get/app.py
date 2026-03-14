from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import json
import boto3
import os
from boto3.dynamodb.conditions import Attr, Key

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

dynamodb = boto3.resource("dynamodb", endpoint_url=os.environ.get("DYNAMODB_ENDPOINT"))

TABLE_NAME = os.environ["DYNAMODB_FIRMWARE_TABLE_NAME"]
firmware_table = dynamodb.Table(TABLE_NAME)

# Exclude large/internal fields from list responses to keep payloads small.
# The single-item GET returns the full record.
LIST_EXCLUDE_FIELDS = {"files", "manifest"}


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, indent=4, default=str),
    }


def get_firmware_list(product_id=None, version=None):
    if product_id and version:
        response = firmware_table.query(
            KeyConditionExpression=Key("product_id").eq(product_id),
            FilterExpression=Attr("version").eq(version),
        )
    elif product_id:
        # Query is efficient when filtering by partition key
        response = firmware_table.query(
            KeyConditionExpression=Key("product_id").eq(product_id)
        )
    elif version:
        response = firmware_table.scan(
            FilterExpression=Attr("version").eq(version)
        )
    else:
        # Full scan is acceptable given the small expected table size (<1000 items)
        response = firmware_table.scan()

    items = [
        {k: v for k, v in item.items() if k not in LIST_EXCLUDE_FIELDS}
        for item in response.get("Items", [])
    ]
    logger.debug(f"Returning {len(items)} firmware items (product_id='{product_id}' version='{version}')")
    return _response(200, {"items": items})


def get_firmware_item(zip_name):
    # zip_name (UUID) is the unique identifier for a specific build.
    # Scan is used because zip_name is not the DynamoDB primary key.
    response = firmware_table.scan(
        FilterExpression=Attr("zip_name").eq(zip_name)
    )
    items = response.get("Items", [])
    if not items:
        logger.debug(f"Firmware not found: zip_name='{zip_name}'")
        return _response(404, {"message": f"Firmware not found: {zip_name}"})

    logger.debug(f"Returning firmware: zip_name='{zip_name}'")
    return _response(200, items[0])


def lambda_handler(event, context):
    try:
        path_params = event.get("pathParameters") or {}
        zip_name = path_params.get("zip_name")

        if zip_name:
            logger.debug(f"GET /firmware/{zip_name}")
            return get_firmware_item(zip_name)
        else:
            query_params = event.get("queryStringParameters") or {}
            filter_product_id = query_params.get("product_id")
            filter_version = query_params.get("version")
            logger.debug(f"GET /firmware product_id='{filter_product_id}' version='{filter_version}'")
            return get_firmware_list(product_id=filter_product_id, version=filter_version)

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
