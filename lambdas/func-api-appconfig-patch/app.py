"""
PATCH /appconfig/{application} — update the logging configuration for an AppConfig application.

Requires the caller to be in the super_users group.

Path parameter:
  application — the AppConfig application name (matches the Lambda function name)

Request body:
  {
    "logging": [{"prefix": "LEVEL"}, ...]
  }

Each entry in the logging array is a single-key object mapping a function name
prefix to a log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

A new hosted configuration version is created and immediately deployed using
the AllAtOnce deployment strategy.
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
DEPLOYMENT_STRATEGY = "AppConfig.AllAtOnce"
VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


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


def _find_app(application_name):
    """Return (app_id, env_id, profile_id) for the named application, or None if not found."""
    app_paginator = appconfig.get_paginator("list_applications")
    for page in app_paginator.paginate():
        for app in page.get("Items", []):
            if app["Name"] == application_name:
                app_id = app["Id"]

                # Find the environment
                env_id = None
                env_paginator = appconfig.get_paginator("list_environments")
                for env_page in env_paginator.paginate(ApplicationId=app_id):
                    for env in env_page.get("Items", []):
                        if env["Name"] == ENVIRONMENT_NAME:
                            env_id = env["Id"]
                            break
                    if env_id:
                        break

                if not env_id:
                    return None

                # Find the logging profile
                profile_id = None
                profile_paginator = appconfig.get_paginator("list_configuration_profiles")
                for profile_page in profile_paginator.paginate(ApplicationId=app_id):
                    for profile in profile_page.get("Items", []):
                        if profile["Name"] == PROFILE_NAME:
                            profile_id = profile["Id"]
                            break
                    if profile_id:
                        break

                if not profile_id:
                    return None

                return app_id, env_id, profile_id

    return None


def lambda_handler(event, context):
    try:
        if not _is_super_user(event):
            return _response(403, {"message": "Forbidden"})

        application_name = (event.get("pathParameters") or {}).get("application", "").strip()
        if not application_name:
            return _response(400, {"message": "Missing path parameter: application"})

        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _response(400, {"message": "Invalid JSON body"})

        logging_config = body.get("logging")
        if logging_config is None:
            return _response(400, {"message": "Missing required field: logging"})
        if not isinstance(logging_config, list):
            return _response(400, {"message": "Field 'logging' must be an array"})

        # Validate each entry: must be a single-key object with a valid log level
        for i, entry in enumerate(logging_config):
            if not isinstance(entry, dict) or len(entry) != 1:
                return _response(400, {"message": f"logging[{i}] must be a single-key object"})
            level = next(iter(entry.values())).upper()
            if level not in VALID_LEVELS:
                return _response(400, {"message": f"logging[{i}] has invalid level '{level}'; must be one of {sorted(VALID_LEVELS)}"})

        # Normalize levels to uppercase
        normalized = [{k: v.upper()} for entry in logging_config for k, v in entry.items()]

        result = _find_app(application_name)
        if result is None:
            return _response(404, {"message": f"Application '{application_name}' not found or has no '{PROFILE_NAME}' profile in environment '{ENVIRONMENT_NAME}'"})

        app_id, env_id, profile_id = result

        # Create a new hosted configuration version
        content_bytes = json.dumps(normalized).encode("utf-8")
        ver_resp = appconfig.create_hosted_configuration_version(
            ApplicationId=app_id,
            ConfigurationProfileId=profile_id,
            Content=content_bytes,
            ContentType="application/json",
        )
        version_number = ver_resp["VersionNumber"]

        # Deploy the new version immediately
        appconfig.start_deployment(
            ApplicationId=app_id,
            EnvironmentId=env_id,
            DeploymentStrategyId=DEPLOYMENT_STRATEGY,
            ConfigurationProfileId=profile_id,
            ConfigurationVersion=str(version_number),
        )

        return _response(200, {
            "application": application_name,
            "version": version_number,
            "logging": normalized,
        })

    except ClientError as e:
        logger.exception("AWS ClientError")
        return _response(500, {"message": str(e)})
    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
