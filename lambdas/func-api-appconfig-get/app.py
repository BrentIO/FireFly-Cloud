"""
GET /appconfig — list all firefly-func-* Lambda functions with their AppConfig configuration.

Requires the caller to be in the super_users group.

Response shape:
  {
    "applications": [
      {
        "name": "firefly-func-api-firmware-get",
        "logging": "WARNING",
        "version": 3,
        "deployed_version": 3,
        "status": "COMPLETE"
      },
      {
        "name": "firefly-func-api-ota-get",
        "logging": null,
        "version": null,
        "deployed_version": null,
        "status": null
      }
    ]
  }

Functions with no AppConfig application appear with null values; they use the
default WARNING level until explicitly configured via PATCH /appconfig/{function_name}.
"""

from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import json
import os

import boto3
from botocore.exceptions import ClientError

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

appconfig = boto3.client("appconfig")
lambda_client = boto3.client("lambda")

SUPER_GROUP = "super_users"
ENVIRONMENT_NAME = "default"
PROFILE_NAME = "logging"
FUNCTION_PREFIX = "firefly-func-"


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


def _list_lambda_functions():
    """Return sorted list of all firefly-func-* Lambda function names."""
    names = []
    paginator = lambda_client.get_paginator("list_functions")
    for page in paginator.paginate():
        for fn in page["Functions"]:
            if fn["FunctionName"].startswith(FUNCTION_PREFIX):
                names.append(fn["FunctionName"])
    return sorted(names)


def _build_appconfig_index():
    """
    Return a dict mapping function_name -> (app_id, env_id, profile_id)
    for all AppConfig applications matching the firefly-func-* naming convention.
    """
    index = {}

    apps = {}
    try:
        paginator = appconfig.get_paginator("list_applications")
        for page in paginator.paginate():
            for app in page.get("Items", []):
                if app["Name"].startswith(FUNCTION_PREFIX):
                    apps[app["Name"]] = app["Id"]
    except ClientError:
        return index

    for app_name, app_id in apps.items():
        env_id = None
        try:
            env_paginator = appconfig.get_paginator("list_environments")
            for page in env_paginator.paginate(ApplicationId=app_id):
                for env in page.get("Items", []):
                    if env["Name"] == ENVIRONMENT_NAME:
                        env_id = env["Id"]
                        break
                if env_id:
                    break
        except ClientError:
            continue

        if not env_id:
            continue

        profile_id = None
        try:
            profile_paginator = appconfig.get_paginator("list_configuration_profiles")
            for page in profile_paginator.paginate(ApplicationId=app_id):
                for profile in page.get("Items", []):
                    if profile["Name"] == PROFILE_NAME:
                        profile_id = profile["Id"]
                        break
                if profile_id:
                    break
        except ClientError:
            continue

        if not profile_id:
            continue

        index[app_name] = (app_id, env_id, profile_id)

    return index


def _get_app_details(app_id, env_id, profile_id):
    """Return (logging_level, latest_version, deployed_version, status)."""
    logging_level = None
    latest_version = None
    deployed_version = None
    status = None

    try:
        resp = appconfig.list_hosted_configuration_versions(
            ApplicationId=app_id,
            ConfigurationProfileId=profile_id,
            MaxResults=1,
        )
        versions = resp.get("Items", [])
        if versions:
            latest_version = versions[0]["VersionNumber"]
            ver_resp = appconfig.get_hosted_configuration_version(
                ApplicationId=app_id,
                ConfigurationProfileId=profile_id,
                VersionNumber=latest_version,
            )
            content = ver_resp["Content"].read()
            if content:
                config = json.loads(content)
                logging_level = config.get("logging")
    except (ClientError, json.JSONDecodeError):
        pass

    try:
        resp = appconfig.list_deployments(
            ApplicationId=app_id,
            EnvironmentId=env_id,
            MaxResults=1,
        )
        deployments = resp.get("Items", [])
        if deployments:
            d = deployments[0]
            deployed_version = int(d.get("ConfigurationVersion", 0)) or None
            status = d.get("State")
    except ClientError:
        pass

    return logging_level, latest_version, deployed_version, status


def lambda_handler(event, context):
    try:
        if not _is_super_user(event):
            return _response(403, {"message": "Forbidden"})

        function_names = _list_lambda_functions()
        appconfig_index = _build_appconfig_index()

        applications = []
        for name in function_names:
            entry = {
                "name": name,
                "logging": None,
                "version": None,
                "deployed_version": None,
                "status": None,
            }

            if name in appconfig_index:
                app_id, env_id, profile_id = appconfig_index[name]
                logging_level, latest_version, deployed_version, status = _get_app_details(
                    app_id, env_id, profile_id
                )
                entry["logging"] = logging_level
                entry["version"] = latest_version
                entry["deployed_version"] = deployed_version
                entry["status"] = status

            applications.append(entry)

        return _response(200, {"applications": applications})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
