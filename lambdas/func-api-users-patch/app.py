"""
PATCH /users/{email} — update a user's super user status.

Body: { "is_super": true | false }

Rules:
- Caller must be in super_users group.
- The last super user cannot be demoted (super count must not reach zero).
"""

from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import json
import os

import boto3

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

cognito = boto3.client("cognito-idp")
USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]
SUPER_GROUP = "super_users"


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, indent=4, default=str),
    }


def _get_claims(event):
    return (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )


def _is_super_user(event):
    groups_raw = _get_claims(event).get("cognito:groups", "")
    if not groups_raw:
        return False
    try:
        groups = json.loads(groups_raw)
        return SUPER_GROUP in groups
    except (json.JSONDecodeError, TypeError):
        return SUPER_GROUP in groups_raw.strip("[]").split()


def _get_caller_email(event):
    claims = _get_claims(event)
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
    return username


def _get_super_user_emails():
    super_emails = set()
    paginator = cognito.get_paginator("list_users_in_group")
    for page in paginator.paginate(UserPoolId=USER_POOL_ID, GroupName=SUPER_GROUP):
        for user in page.get("Users", []):
            for attr in user.get("Attributes", []):
                if attr["Name"] == "email":
                    super_emails.add(attr["Value"].lower())
    return super_emails


def _find_cognito_username(email):
    """Return the Cognito Username for a given email, or None."""
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

        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _response(400, {"message": "Invalid JSON body"})

        if "is_super" not in body:
            return _response(400, {"message": "is_super is required"})

        caller_email = _get_caller_email(event)
        is_super = body["is_super"]

        if not isinstance(is_super, bool):
            return _response(400, {"message": "is_super must be a boolean"})

        cognito_username = _find_cognito_username(email)
        if not cognito_username:
            return _response(404, {"message": f"User '{email}' not found in Cognito"})

        super_emails = _get_super_user_emails()
        currently_super = email in super_emails

        if not is_super and currently_super and len(super_emails) <= 1:
            return _response(
                409,
                {
                    "message": "Cannot remove super status from the last super user. "
                    "Promote another user first."
                },
            )

        if is_super and not currently_super:
            cognito.admin_add_user_to_group(
                UserPoolId=USER_POOL_ID,
                Username=cognito_username,
                GroupName=SUPER_GROUP,
            )
            logger.info("Promoted %s to super user by %s", email, caller_email)
        elif not is_super and currently_super:
            cognito.admin_remove_user_from_group(
                UserPoolId=USER_POOL_ID,
                Username=cognito_username,
                GroupName=SUPER_GROUP,
            )
            logger.info("Demoted %s from super user by %s", email, caller_email)

        return _response(200, {"email": email, "is_super": is_super})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
