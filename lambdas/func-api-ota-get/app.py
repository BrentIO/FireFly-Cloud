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
    if name.endswith(".merged.bin"):
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

        query_params = event.get("queryStringParameters") or {}
        current_version = query_params.get("current_version")

        if not current_version:
            return _response(400, {"message": "current_version is required"})

        logger.debug(
            f"GET OTA product_id='{product_id}' application='{application}' "
            f"current_version='{current_version}'"
        )

        pk = f"{product_id}#{application}"

        response = firmware_table.query(
            KeyConditionExpression=Key("pk").eq(pk),
            FilterExpression=Attr("release_status").eq("RELEASED"),
            ConsistentRead=True,
        )
        items = response.get("Items", [])

        if not items:
            # Check if current_version exists but is REVOKED (no newer release available).
            # Uses Query (not GetItem) since only dynamodb:Query is permitted on this function.
            check = firmware_table.query(
                KeyConditionExpression=Key("pk").eq(pk) & Key("version").eq(current_version),
                FilterExpression=Attr("release_status").eq("REVOKED"),
                ConsistentRead=True,
            )
            if check.get("Items"):
                return _response(409, {
                    "message": f"Current version '{current_version}' is no longer released and no newer version is available"
                })
            return _response(404, {
                "message": f"No released firmware found for product_id='{product_id}' application='{application}'"
            })

        # Find the oldest RELEASED version strictly greater than current_version.
        # Version strings use YYYY.MM.bb format which sorts correctly lexicographically.
        later = [i for i in items if i.get("version", "") > current_version]
        if later:
            item = min(later, key=lambda x: x.get("version", ""))
        else:
            # No newer version — check if current_version is still RELEASED.
            current_item = next((i for i in items if i.get("version") == current_version), None)
            if current_item:
                # Device is up to date. Return the same version manifest so the
                # esp32FOTA library receives 200 OK and semver_compare returns 0 (no update).
                item = current_item
            else:
                # current_version is no longer RELEASED (revoked) and nothing newer exists.
                return _response(409, {
                    "message": f"Current version '{current_version}' is no longer released and no newer version is available"
                })

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
