"""
GET /devices — list all registered devices.

Requires the caller to be in the super_users group.

Response:
  { "devices": [ { uuid, product_id, product_hex, device_class, registration_date,
                    registering_application, registering_version, mcu,
                    network?, partitions? } ] }
"""

import json
import os

import boto3

from shared.app_config import get_appconfig
from shared.logging_config import configure_logger

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

dynamodb = boto3.resource("dynamodb")
DEVICES_TABLE_NAME = os.environ["DYNAMODB_DEVICES_TABLE_NAME"]
devices_table = dynamodb.Table(DEVICES_TABLE_NAME)

SUPER_GROUP = "super_users"


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, indent=4, default=str),
    }


def _is_super_user(event):
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    groups_raw = claims.get("cognito:groups", "")
    if not groups_raw:
        return False
    try:
        groups = json.loads(groups_raw)
        return SUPER_GROUP in groups
    except (json.JSONDecodeError, TypeError):
        return SUPER_GROUP in groups_raw.strip("[]").split()


def lambda_handler(event, context):
    try:
        if not _is_super_user(event):
            return _response(403, {"message": "Forbidden"})

        devices = []
        paginator = dynamodb.meta.client.get_paginator("scan")
        for page in paginator.paginate(TableName=DEVICES_TABLE_NAME):
            for item in page.get("Items", []):
                devices.append(item)

        devices.sort(key=lambda d: d.get("registration_date", ""))
        return _response(200, {"devices": devices})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
