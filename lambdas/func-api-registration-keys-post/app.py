"""
POST /registration-keys — generate a one-time device registration key.

Requires the caller to be a registered FireFly-Cloud user (Cognito JWT).
Generates a 6-character uppercase alphanumeric key, stores it in DynamoDB
with a 30-minute TTL, and returns it to the caller.

The caller shares the key with a manufacturing operator who enters it in
the HW-Reg UI to complete device registration.
"""

import json
import os
import random
import string
import time

import boto3

from shared.app_config import get_appconfig
from shared.logging_config import configure_logger

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

dynamodb = boto3.resource("dynamodb")
REGISTRATION_KEYS_TABLE_NAME = os.environ["DYNAMODB_REGISTRATION_KEYS_TABLE_NAME"]
registration_keys_table = dynamodb.Table(REGISTRATION_KEYS_TABLE_NAME)

KEY_TTL_SECONDS = 1800
KEY_LENGTH = 6
KEY_ALPHABET = string.ascii_uppercase + string.digits


def _response(status_code, body=None):
    resp = {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
    }
    resp["body"] = json.dumps(body, indent=4, default=str) if body is not None else ""
    return resp


def _is_authenticated(event):
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    return bool(claims.get("sub"))


def lambda_handler(event, context):
    try:
        if not _is_authenticated(event):
            return _response(401, {"message": "Unauthorized"})

        key = "".join(random.SystemRandom().choices(KEY_ALPHABET, k=KEY_LENGTH))
        ttl = int(time.time()) + KEY_TTL_SECONDS

        registration_keys_table.put_item(Item={"key": key, "ttl": ttl})

        logger.info("Registration key generated (TTL: %ds)", KEY_TTL_SECONDS)
        return _response(201, {"key": key})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
