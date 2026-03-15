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
UI_ORIGIN = os.environ.get("UI_ORIGIN", "")
firmware_table = dynamodb.Table(TABLE_NAME)

# Exclude large/internal fields from list responses to keep payloads small.
# The single-item GET returns the full record. pk is always excluded (internal).
LIST_EXCLUDE_FIELDS = {"files", "manifest", "pk"}


def _response(status_code, body, origin=None):
    headers = {"Content-Type": "application/json"}
    if origin and UI_ORIGIN and origin == UI_ORIGIN:
        headers["Access-Control-Allow-Origin"] = origin
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, indent=4, default=str),
    }


def get_firmware_list(product_id=None, application=None, version=None, origin=None):
    filter_parts = []
    if application:
        filter_parts.append(Attr("application").eq(application))
    if version:
        filter_parts.append(Attr("version").eq(version))

    filter_expr = None
    for part in filter_parts:
        filter_expr = part if filter_expr is None else filter_expr & part

    kwargs = {}
    if filter_expr is not None:
        kwargs["FilterExpression"] = filter_expr

    if product_id:
        response = firmware_table.query(
            IndexName="product_id-index",
            KeyConditionExpression=Key("product_id").eq(product_id),
            **kwargs
        )
    else:
        # Full scan is acceptable given the small expected table size (<1000 items)
        response = firmware_table.scan(**kwargs)

    items = [
        {k: v for k, v in item.items() if k not in LIST_EXCLUDE_FIELDS}
        for item in response.get("Items", [])
    ]
    logger.debug(f"Returning {len(items)} firmware items (product_id='{product_id}' application='{application}' version='{version}')")
    return _response(200, {"items": items}, origin=origin)


def get_firmware_item(zip_name, origin=None):
    # Query GSI 2 by zip_name (UUID) — the unique identifier for a specific build.
    response = firmware_table.query(
        IndexName="zip_name-index",
        KeyConditionExpression=Key("zip_name").eq(zip_name)
    )
    items = response.get("Items", [])
    if not items:
        logger.debug(f"Firmware not found: zip_name='{zip_name}'")
        return _response(404, {"message": f"Firmware not found: {zip_name}"}, origin=origin)

    item = {k: v for k, v in items[0].items() if k != "pk"}
    logger.debug(f"Returning firmware: zip_name='{zip_name}'")
    return _response(200, item, origin=origin)


def lambda_handler(event, context):
    try:
        origin = (event.get("headers") or {}).get("origin", "")
        path_params = event.get("pathParameters") or {}
        zip_name = path_params.get("zip_name")

        if zip_name:
            logger.debug(f"GET /firmware/{zip_name}")
            return get_firmware_item(zip_name, origin=origin)
        else:
            query_params = event.get("queryStringParameters") or {}
            filter_product_id = query_params.get("product_id")
            filter_application = query_params.get("application")
            filter_version = query_params.get("version")
            logger.debug(f"GET /firmware product_id='{filter_product_id}' application='{filter_application}' version='{filter_version}'")
            return get_firmware_list(product_id=filter_product_id, application=filter_application, version=filter_version, origin=origin)

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
