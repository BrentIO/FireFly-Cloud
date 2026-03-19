"""
POST /users — add a user to the allowed list (invite).

Body: { "email": "...", "environments": ["dev", "prod"] }

Requires the caller to be in the super_users group.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ["DYNAMODB_USERS_TABLE_NAME"]
SUPER_GROUP = "super_users"

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
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    return claims.get("email", "").lower()


def lambda_handler(event, context):
    try:
        if not _is_super_user(event):
            return _response(403, {"message": "Forbidden"})

        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _response(400, {"message": "Invalid JSON body"})

        email = (body.get("email") or "").strip().lower()
        environments = body.get("environments", [])

        if not email:
            return _response(400, {"message": "email is required"})

        if not EMAIL_RE.match(email):
            return _response(400, {"message": "email is not a valid email address"})

        if not isinstance(environments, list) or not environments:
            return _response(
                400, {"message": "environments must be a non-empty list (e.g. [\"dev\", \"prod\"])"}
            )

        valid_envs = {"dev", "production"}
        invalid = [e for e in environments if e not in valid_envs]
        if invalid:
            return _response(
                400,
                {"message": f"Invalid environment(s): {invalid}. Must be one of: {sorted(valid_envs)}"},
            )

        caller_email = _get_caller_email(event)
        now = datetime.now(timezone.utc).isoformat()

        users_table.put_item(
            Item={
                "email": email,
                "environments": environments,
                "invited_by": caller_email,
                "created_at": now,
            },
            # Fail if user already exists
            ConditionExpression="attribute_not_exists(email)",
        )

        logger.info(f"User invited: {email} by {caller_email}, environments: {environments}")
        return _response(201, {"email": email, "environments": environments})

    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return _response(409, {"message": f"User '{email}' is already in the allowed list"})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
