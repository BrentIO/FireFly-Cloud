"""
GET /users — list all Cognito users with super-user status.
Requires the caller to be in the super_users group.
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


def lambda_handler(event, context):
    try:
        if not _is_super_user(event):
            return _response(403, {"message": "Forbidden"})

        super_emails = _get_super_user_emails()

        users = []
        paginator = cognito.get_paginator("list_users")
        for page in paginator.paginate(UserPoolId=USER_POOL_ID):
            for user in page.get("Users", []):
                attrs = {a["Name"]: a["Value"] for a in user.get("Attributes", [])}
                email = attrs.get("email", "").lower()
                if not email:
                    continue
                users.append(
                    {
                        "email": email,
                        "name": attrs.get("name"),
                        "environments": attrs.get("custom:environments", ""),
                        "is_super": email in super_emails,
                        "status": user.get("UserStatus"),
                        "created": user.get("UserCreateDate"),
                    }
                )

        users.sort(key=lambda u: u["email"])
        return _response(200, {"users": users})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
