"""
Cognito pre-signup Lambda trigger.

Fires before a new user is created in the User Pool. Blocks sign-in for any
Google account that has not been added to the firefly-users allowed list AND
has access to the current environment.

Admin-created users (test users, first super user bootstrap) always pass through.
"""

from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import boto3
import os
import time

from boto3.dynamodb.conditions import Key

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ["DYNAMODB_USERS_TABLE_NAME"]
ENVIRONMENT_NAME = os.environ["ENVIRONMENT_NAME"]

users_table = dynamodb.Table(TABLE_NAME)


def lambda_handler(event, context):
    trigger_source = event.get("triggerSource", "")
    logger.info(f"Pre-signup trigger: {trigger_source}")

    # Admin-created users (e.g., test users or first super user setup) bypass
    # the allowed list check entirely.
    if trigger_source in ("PreSignUp_AdminCreateUser",):
        event["response"]["autoConfirmUser"] = True
        return event

    email = (
        event.get("request", {})
        .get("userAttributes", {})
        .get("email", "")
        .lower()
        .strip()
    )

    if not email:
        logger.warning("Pre-signup blocked: no email in user attributes")
        raise Exception("Sign-in is not permitted: no email address was provided.")

    response = users_table.get_item(Key={"email": email})
    item = response.get("Item")

    if not item:
        logger.warning(f"Pre-signup blocked: {email} not in allowed list")
        raise Exception(
            "Sign-in is not permitted: this account has not been granted access."
        )

    expires_at = item.get("expires_at")
    if expires_at is not None and int(expires_at) < int(time.time()):
        logger.warning(f"Pre-signup blocked: invitation for {email} has expired")
        raise Exception(
            "Sign-in is not permitted: this invitation has expired. Please ask a super user to re-invite you."
        )

    environments = item.get("environments", [])
    if isinstance(environments, set):
        environments = list(environments)

    if ENVIRONMENT_NAME not in environments:
        logger.warning(
            f"Pre-signup blocked: {email} not allowed in environment '{ENVIRONMENT_NAME}'"
        )
        raise Exception(
            f"Sign-in is not permitted: this account does not have access to the '{ENVIRONMENT_NAME}' environment."
        )

    logger.info(f"Pre-signup allowed: {email}")
    return event
