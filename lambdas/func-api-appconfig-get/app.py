"""
GET /appconfig — return the current logging configuration for the "firefly" AppConfig application.

Requires the caller to be in the super_users group.

Response shape:
  {
    "logging": [{"prefix": "LEVEL"}, ...]
  }

Returns {"logging": []} if the application or its logging profile does not yet exist.
"""

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

appconfig = boto3.client("appconfig")
SUPER_GROUP = "super_users"
ENVIRONMENT_NAME = os.environ["ENVIRONMENT_NAME"]
APP_NAME = "firefly"
PROFILE_NAME = "logging"


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


def _find_firefly_app():
    """Return (app_id, env_id, profile_id) for the 'firefly' application, or None if not found."""
    paginator = appconfig.get_paginator("list_applications")
    for page in paginator.paginate():
        for app in page.get("Items", []):
            if app["Name"] == APP_NAME:
                app_id = app["Id"]

                env_id = None
                try:
                    env_paginator = appconfig.get_paginator("list_environments")
                    for env_page in env_paginator.paginate(ApplicationId=app_id):
                        for env in env_page.get("Items", []):
                            if env["Name"] == ENVIRONMENT_NAME:
                                env_id = env["Id"]
                                break
                        if env_id:
                            break
                except ClientError:
                    return None

                if not env_id:
                    return None

                profile_id = None
                try:
                    profile_paginator = appconfig.get_paginator("list_configuration_profiles")
                    for profile_page in profile_paginator.paginate(ApplicationId=app_id):
                        for profile in profile_page.get("Items", []):
                            if profile["Name"] == PROFILE_NAME:
                                profile_id = profile["Id"]
                                break
                        if profile_id:
                            break
                except ClientError:
                    return None

                if not profile_id:
                    return None

                return app_id, env_id, profile_id

    return None


def _get_logging_config(app_id, profile_id):
    """Return the content of the most recent hosted configuration version, or None."""
    try:
        resp = appconfig.list_hosted_configuration_versions(
            ApplicationId=app_id,
            ConfigurationProfileId=profile_id,
            MaxResults=1,
        )
        versions = resp.get("Items", [])
        if not versions:
            return None

        latest_version = versions[0]["VersionNumber"]
        ver_resp = appconfig.get_hosted_configuration_version(
            ApplicationId=app_id,
            ConfigurationProfileId=profile_id,
            VersionNumber=latest_version,
        )
        content = ver_resp["Content"].read()
        return json.loads(content) if content else None
    except (ClientError, json.JSONDecodeError):
        return None


def lambda_handler(event, context):
    try:
        if not _is_super_user(event):
            return _response(403, {"message": "Forbidden"})

        result = _find_firefly_app()
        if result is None:
            return _response(200, {"logging": []})

        app_id, env_id, profile_id = result
        logging_config = _get_logging_config(app_id, profile_id)

        return _response(200, {"logging": logging_config or []})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
