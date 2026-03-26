"""
GET /users — list all users: Cognito accounts merged with invited-only DynamoDB records.

Requires the caller to be in the super_users group.

Response includes:
  - Users who have signed in (from Cognito)
  - Users who were invited but have not yet signed in (DynamoDB-only), status = "INVITED"
  - Expired invitations (expires_at in the past) are excluded
"""

from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import json
import os
import time

import boto3

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


def _scan_dynamodb_users():
    """
    Return all non-expired DynamoDB user records keyed by email.

    Records with an expires_at timestamp in the past are excluded so that
    expired invitations are not surfaced in the list.
    """
    now = int(time.time())
    result = {}
    paginator = dynamodb.meta.client.get_paginator("scan")
    for page in paginator.paginate(TableName=TABLE_NAME):
        for item in page.get("Items", []):
            email = item.get("email", "").lower()
            if not email:
                continue
            expires_at = item.get("expires_at")
            if expires_at is not None and int(expires_at) < now:
                continue  # expired invitation
            result[email] = item
    return result


def lambda_handler(event, context):
    try:
        if not _is_super_user(event):
            return _response(403, {"message": "Forbidden"})

        super_emails = _get_super_user_emails()
        db_users = _scan_dynamodb_users()

        users = []
        cognito_emails = set()

        # Cognito users (have signed in at least once)
        paginator = cognito.get_paginator("list_users")
        for page in paginator.paginate(UserPoolId=USER_POOL_ID):
            for user in page.get("Users", []):
                attrs = {a["Name"]: a["Value"] for a in user.get("Attributes", [])}
                email = attrs.get("email", "").lower()
                if not email:
                    continue
                cognito_emails.add(email)
                db_item = db_users.get(email, {})
                users.append(
                    {
                        "email": email,
                        "name": attrs.get("name"),
                        "is_super": email in super_emails,
                        "status": user.get("UserStatus"),
                        "created": user.get("UserCreateDate"),
                        "invited_by": db_item.get("invited_by"),
                    }
                )

        # DynamoDB-only users (invited but not yet signed in)
        for email, db_item in db_users.items():
            if email in cognito_emails:
                continue
            users.append(
                {
                    "email": email,
                    "is_super": False,
                    "status": "INVITED",
                    "created": db_item.get("created_at"),
                    "invited_by": db_item.get("invited_by"),
                }
            )

        users.sort(key=lambda u: u["email"])
        return _response(200, {"users": users})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
