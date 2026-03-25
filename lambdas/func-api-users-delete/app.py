"""
DELETE /users/{email} — remove a user from Cognito and the allowed list.

Rules:
- Caller must be in super_users group.
- The last super user cannot be deleted (super count must not reach zero).
"""

from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import json
import os

import boto3
from boto3.dynamodb.conditions import Key

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

cognito = boto3.client("cognito-idp")
dynamodb = boto3.resource("dynamodb")
USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]
TABLE_NAME = os.environ["DYNAMODB_USERS_TABLE_NAME"]
SUPER_GROUP = "super_users"

users_table = dynamodb.Table(TABLE_NAME)


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


def _get_super_user_emails():
    super_emails = set()
    paginator = cognito.get_paginator("list_users_in_group")
    for page in paginator.paginate(UserPoolId=USER_POOL_ID, GroupName=SUPER_GROUP):
        for user in page.get("Users", []):
            for attr in user.get("Attributes", []):
                if attr["Name"] == "email":
                    super_emails.add(attr["Value"].lower())
    return super_emails


def _find_cognito_user(email):
    """Return the Cognito Username for a given email, or None if not found."""
    response = cognito.list_users(
        UserPoolId=USER_POOL_ID,
        Filter=f'email = "{email}"',
    )
    users = response.get("Users", [])
    return users[0]["Username"] if users else None


def lambda_handler(event, context):
    try:
        if not _is_super_user(event):
            return _response(403, {"message": "Forbidden"})

        path_params = event.get("pathParameters") or {}
        email = (path_params.get("email") or "").strip().lower()

        if not email:
            return _response(400, {"message": "email path parameter is required"})

        super_emails = _get_super_user_emails()
        target_is_super = email in super_emails

        if target_is_super and len(super_emails) <= 1:
            return _response(
                409,
                {
                    "message": "Cannot delete the last super user. "
                    "Promote another user to super first."
                },
            )

        # Remove from Cognito (user may not have signed in yet — allowed list only)
        cognito_username = _find_cognito_user(email)
        if cognito_username:
            cognito.admin_delete_user(
                UserPoolId=USER_POOL_ID,
                Username=cognito_username,
            )
            logger.info(f"Deleted Cognito user: {email} (username: {cognito_username})")
        else:
            logger.info(f"No Cognito user found for {email} — removing from allowed list only")

        # Remove from allowed list
        users_table.delete_item(Key={"email": email})

        logger.info(f"Deleted user: {email}")
        return _response(200, {"message": f"User '{email}' has been deleted"})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
