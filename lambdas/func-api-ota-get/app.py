from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import json
import boto3
import os
from boto3.dynamodb.conditions import Key, Attr

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

dynamodb = boto3.resource("dynamodb", endpoint_url=os.environ.get("DYNAMODB_ENDPOINT"))

TABLE_NAME = os.environ["DYNAMODB_FIRMWARE_TABLE_NAME"]
CLOUDFRONT_DOMAIN = os.environ["CLOUDFRONT_DOMAIN"]
FIRMWARE_TYPE_MAP = json.loads(os.environ["FIRMWARE_TYPE_MAP"])

firmware_table = dynamodb.Table(TABLE_NAME)

LFS_BINARY_NAME = "www.bin"
EXCLUDE_FROM_OTA = {"config.bin", "manifest.json"}


def _is_main_binary(name):
    """Return True if name is the main application firmware binary."""
    if name in EXCLUDE_FROM_OTA:
        return False
    if name == LFS_BINARY_NAME:
        return False
    if name.endswith(".bootloader.bin") or name.endswith(".partitions.bin"):
        return False
    return name.endswith(".bin")


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
        application = path_params.get("application")

        logger.debug(f"GET OTA product_id='{product_id}' application='{application}'")

        pk = f"{product_id}#{application}"

        response = firmware_table.query(
            KeyConditionExpression=Key("pk").eq(pk),
            FilterExpression=Attr("release_status").eq("RELEASED"),
        )
        items = response.get("Items", [])

        if not items:
            return _response(404, {
                "message": f"No released firmware found for product_id='{product_id}' application='{application}'"
            })

        # Select the most recently processed build.
        item = max(items, key=lambda x: x.get("uploaded_at", 0))
        version = item["version"]
        files = item.get("files", [])

        base_url = f"https://{CLOUDFRONT_DOMAIN}/{product_id}/{application}/{version}"

        url = None
        littlefs = None

        for f in files:
            name = f["name"]
            if name == LFS_BINARY_NAME:
                littlefs = f"{base_url}/{name}"
            elif _is_main_binary(name) and url is None:
                url = f"{base_url}/{name}"

        if not url:
            logger.error(f"No main binary found in files: {[f['name'] for f in files]}")
            return _response(500, {"message": "No main firmware binary found in released record"})

        firmware_type = FIRMWARE_TYPE_MAP.get(application)
        if not firmware_type:
            logger.error(f"No firmware type mapping found for application='{application}'")
            return _response(500, {"message": f"No firmware type mapping found for application='{application}'"})

        manifest = {
            "type": firmware_type,
            "version": version,
            "url": url,
        }
        if littlefs:
            manifest["littlefs"] = littlefs

        return _response(200, manifest)

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
