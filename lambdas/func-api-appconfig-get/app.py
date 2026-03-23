"""
GET /appconfig — list all AppConfig applications that have a "logging" profile
in the current environment, along with the current logging configuration.

Requires the caller to be in the super_users group.

Response shape:
  {
    "applications": [
      {
        "id": "<appconfig-app-id>",
        "name": "<lambda-function-name>",
        "environment_id": "<appconfig-env-id>",
        "profile_id": "<appconfig-profile-id>",
        "logging": [{"prefix": "LEVEL"}, ...]
      }
    ]
  }
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

        applications = []

        app_paginator = appconfig.get_paginator("list_applications")
        for app_page in app_paginator.paginate():
            for app in app_page.get("Items", []):
                app_id = app["Id"]
                app_name = app["Name"]

                # Find the environment matching our deployment environment
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
                    continue

                if not env_id:
                    continue

                # Find the logging configuration profile
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
                    continue

                if not profile_id:
                    continue

                logging_config = _get_logging_config(app_id, profile_id)

                applications.append({
                    "id": app_id,
                    "name": app_name,
                    "environment_id": env_id,
                    "profile_id": profile_id,
                    "logging": logging_config,
                })

        applications.sort(key=lambda a: a["name"])
        return _response(200, {"applications": applications})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
