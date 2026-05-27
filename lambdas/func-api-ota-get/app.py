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

LFS_BINARY_NAME = "ui.bin"


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _build_manifest(item, device_class, product_hex):
    version = item["version"]
    files = item.get("files", [])
    firmware_type = item.get("firmware_type")
    main_binary = item.get("main_binary")

    base_url = f"https://{CLOUDFRONT_DOMAIN}/{device_class}/{product_hex}/{version}"

    app_url = None
    ui_url = None
    for f in files:
        name = f["name"]
        if name == LFS_BINARY_NAME:
            ui_url = f"{base_url}/{name}"
        elif main_binary and name == main_binary:
            app_url = f"{base_url}/{name}"
        elif not main_binary and name.endswith(".ino.bin"):
            app_url = f"{base_url}/{name}"

    if not app_url:
        return None

    binaries = [{"partition": "app", "url": app_url}]
    if ui_url:
        binaries.append({"partition": "ui", "url": ui_url})

    manifest = {
        "application_name": firmware_type,
        "version": version,
        "binaries": binaries,
    }
    if item.get("release_url"):
        manifest["release_url"] = item["release_url"]

    return manifest


def lambda_handler(event, context):
    try:
        path_params = event.get("pathParameters") or {}
        device_class = (path_params.get("class") or "").lower()
        product_hex = (path_params.get("product_hex") or "").lower()
        application = (path_params.get("application") or "").lower()

        query_params = event.get("queryStringParameters") or {}
        current_version = query_params.get("current_version")

        logger.debug(
            f"GET OTA class='{device_class}' product_hex='{product_hex}' "
            f"application='{application}' current_version='{current_version}'"
        )

        pk = f"{device_class}#{product_hex}#{application}"

        response = firmware_table.query(
            KeyConditionExpression=Key("pk").eq(pk),
            FilterExpression=Attr("release_status").eq("RELEASED"),
            ConsistentRead=True,
        )
        items = response.get("Items", [])

        if not current_version:
            if not items:
                return _response(404, {
                    "message": f"No released firmware found for class='{device_class}' product_hex='{product_hex}' application='{application}'"
                })
            versions = [
                m for m in (
                    _build_manifest(i, device_class, product_hex)
                    for i in sorted(items, key=lambda x: x.get("version", ""))
                )
                if m is not None
            ]
            return _response(200, versions)

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
                "message": f"No released firmware found for class='{device_class}' product_hex='{product_hex}' application='{application}'"
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
        firmware_type = item.get("firmware_type")

        if not firmware_type:
            logger.error(f"No firmware_type on DynamoDB record for pk='{pk}' version='{version}'")
            return _response(500, {"message": "Firmware record missing firmware_type"})

        manifest = _build_manifest(item, device_class, product_hex)
        if not manifest:
            logger.error(f"No main binary found in files for pk='{pk}' version='{version}'")
            return _response(500, {"message": "No main firmware binary found in released record"})

        return _response(200, manifest)

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
