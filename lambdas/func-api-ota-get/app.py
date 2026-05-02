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

firmware_table = dynamodb.Table(TABLE_NAME)

LFS_BINARY_NAME = "www.bin"


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, indent=4, default=str),
    }


def lambda_handler(event, context):
    try:
        path_params = event.get("pathParameters") or {}
        device_class = (path_params.get("class") or "").lower()
        product_hex = (path_params.get("product_hex") or "").lower()

        query_params = event.get("queryStringParameters") or {}
        current_version = query_params.get("current_version")

        if not current_version:
            return _response(400, {"message": "current_version is required"})

        logger.debug(
            f"GET OTA class='{device_class}' product_hex='{product_hex}' "
            f"current_version='{current_version}'"
        )

        pk = f"{device_class}#{product_hex}"

        response = firmware_table.query(
            KeyConditionExpression=Key("pk").eq(pk),
            FilterExpression=Attr("release_status").eq("RELEASED"),
            ConsistentRead=True,
        )
        items = response.get("Items", [])

        if not items:
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
                "message": f"No released firmware found for class='{device_class}' product_hex='{product_hex}'"
            })

        later = [i for i in items if i.get("version", "") > current_version]
        if later:
            item = min(later, key=lambda x: x.get("version", ""))
        else:
            current_item = next((i for i in items if i.get("version") == current_version), None)
            if current_item:
                item = current_item
            else:
                return _response(409, {
                    "message": f"Current version '{current_version}' is no longer released and no newer version is available"
                })

        version = item["version"]
        files = item.get("files", [])
        firmware_type = item.get("firmware_type")
        main_binary = item.get("main_binary")

        if not firmware_type:
            logger.error(f"No firmware_type on DynamoDB record for pk='{pk}' version='{version}'")
            return _response(500, {"message": "Firmware record missing firmware_type"})

        base_url = f"https://{CLOUDFRONT_DOMAIN}/{device_class}/{product_hex}/{version}"

        url = None
        littlefs = None

        for f in files:
            name = f["name"]
            if name == LFS_BINARY_NAME:
                littlefs = f"{base_url}/{name}"
            elif main_binary and name == main_binary:
                url = f"{base_url}/{name}"
            elif not main_binary and name.endswith(".ino.bin"):
                url = f"{base_url}/{name}"

        if not url:
            logger.error(f"No main binary found in files: {[f['name'] for f in files]}")
            return _response(500, {"message": "No main firmware binary found in released record"})

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
