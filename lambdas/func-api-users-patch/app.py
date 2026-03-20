"""
PATCH /users/{email} — update a user's super status and/or environments.

Body: { "is_super": true | false }
  or: { "environments": ["dev", "production"] }
  or: both fields together

Rules:
- Caller must be in super_users group.
- The last super user cannot be demoted (super count must not reach zero).
- Caller may only grant environments they themselves have access to.
- environments must be a non-empty list of valid values.
"""

import json
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

cognito = boto3.client("cognito-idp")
dynamodb = boto3.resource("dynamodb")
USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]
TABLE_NAME = os.environ["DYNAMODB_USERS_TABLE_NAME"]
SUPER_GROUP = "super_users"
VALID_ENVS = {"dev", "production"}

users_table = dynamodb.Table(TABLE_NAME)


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


def _get_caller_environments(caller_email):
    """
    Return the set of environments the caller may grant.

    Raises LookupError if the caller has no DynamoDB record — every valid user,
    including bootstrapped super users, must have a record in the table.
    """
    if not caller_email:
        raise LookupError("Caller email could not be determined")
    resp = users_table.get_item(Key={"email": caller_email})
    item = resp.get("Item")
    if not item:
        raise LookupError(f"No user record found for caller: {caller_email}")
    envs = item.get("environments", [])
    if isinstance(envs, set):
        return envs
    if isinstance(envs, list):
        return set(envs)
    return set()


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

        if "is_super" not in body and "environments" not in body:
            return _response(400, {"message": "At least one of is_super or environments is required"})

        caller_email = _get_caller_email(event)
        result = {"email": email}

        # ── environments update ───────────────────────────────────────────────
        if "environments" in body:
            environments = body["environments"]

            if not isinstance(environments, list) or not environments:
                return _response(
                    400, {"message": "environments must be a non-empty list"}
                )

            invalid = [e for e in environments if e not in VALID_ENVS]
            if invalid:
                return _response(
                    400,
                    {"message": f"Invalid environment(s): {invalid}. Must be one of: {sorted(VALID_ENVS)}"},
                )

            try:
                caller_envs = _get_caller_environments(caller_email)
            except LookupError as e:
                logger.warning("Environment lookup failed for caller %s: %s", caller_email, e)
                return _response(403, {"message": "Forbidden"})

            unauthorized = [e for e in environments if e not in caller_envs]
            if unauthorized:
                return _response(
                    403,
                    {"message": f"You do not have access to environment(s): {unauthorized}"},
                )

            users_table.update_item(
                Key={"email": email},
                UpdateExpression="SET environments = :envs",
                ExpressionAttributeValues={":envs": environments},
            )
            logger.info("Updated environments for %s to %s by %s", email, environments, caller_email)
            result["environments"] = environments

        # ── is_super update ───────────────────────────────────────────────────
        if "is_super" in body:
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

            result["is_super"] = is_super

        return _response(200, result)

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
