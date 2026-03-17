"""
PATCH /users/{email} — promote or demote a user's super status.

Body: { "is_super": true | false }

Rules:
- Caller must be in super_users group.
- The last super user cannot be demoted (super count must not reach zero).
"""

import json
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

cognito = boto3.client("cognito-idp")
USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]
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
        return SUPER_GROUP in groups_raw.split()


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
            return _response(400, {"message": "is_super (boolean) is required"})

        is_super = body["is_super"]
        if not isinstance(is_super, bool):
            return _response(400, {"message": "is_super must be a boolean"})

        cognito_username = _find_cognito_username(email)
        if not cognito_username:
            return _response(404, {"message": f"User '{email}' not found"})

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
            logger.info(f"Promoted {email} to super user")
        elif not is_super and currently_super:
            cognito.admin_remove_user_from_group(
                UserPoolId=USER_POOL_ID,
                Username=cognito_username,
                GroupName=SUPER_GROUP,
            )
            logger.info(f"Demoted {email} from super user")
        else:
            logger.info(f"No change for {email}: is_super={is_super}, currently_super={currently_super}")

        return _response(200, {"email": email, "is_super": is_super})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
