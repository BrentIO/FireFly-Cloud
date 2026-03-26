"""
POST /users — add a user to the allowed list (invite).

Body: { "email": "..." }

Requires the caller to be in the super_users group.
"""

from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import json
import os
import re
from datetime import datetime, timezone, timedelta

import boto3

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

cognito = boto3.client("cognito-idp")
dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ["DYNAMODB_USERS_TABLE_NAME"]
USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]
SUPER_GROUP = "super_users"
INVITE_TTL_HOURS = 24

users_table = dynamodb.Table(TABLE_NAME)

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


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


def _get_caller_email(event):
    """
    Return the caller's email address from the JWT claims.

    Cognito access tokens for Google-federated users do not include an email
    claim, so fall back to an AdminGetUser lookup using the username claim.
    """
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    email = claims.get("email", "").lower().strip()
    if email:
        return email

    username = claims.get("username", "").strip()
    if not username:
        return ""

    try:
        resp = cognito.admin_get_user(UserPoolId=USER_POOL_ID, Username=username)
        for attr in resp.get("UserAttributes", []):
            if attr["Name"] == "email":
                return attr["Value"].lower().strip()
    except Exception:
        logger.warning("Could not look up caller email for username: %s", username)

    return username  # last resort: store the Cognito username


def lambda_handler(event, context):
    try:
        if not _is_super_user(event):
            return _response(403, {"message": "Forbidden"})

        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _response(400, {"message": "Invalid JSON body"})

        email = (body.get("email") or "").strip().lower()

        if not email:
            return _response(400, {"message": "email is required"})

        if not EMAIL_RE.match(email):
            return _response(400, {"message": "email is not a valid email address"})

        caller_email = _get_caller_email(event)

        now = datetime.now(timezone.utc)
        expires_at = int((now + timedelta(hours=INVITE_TTL_HOURS)).timestamp())

        users_table.put_item(
            Item={
                "email": email,
                "invited_by": caller_email,
                "created_at": now.isoformat(),
                "expires_at": expires_at,
            },
            # Fail if user already exists
            ConditionExpression="attribute_not_exists(email)",
        )

        logger.info(f"User invited: {email} by {caller_email}")
        return _response(201, {"email": email})

    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return _response(409, {"message": f"User '{email}' is already in the allowed list"})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
