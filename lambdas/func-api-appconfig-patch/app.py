"""
PATCH /appconfig — update the logging configuration for the "firefly" AppConfig application.

Requires the caller to be in the super_users group.

Request body:
  {
    "logging": [{"prefix": "LEVEL"}, ...]
  }

Each entry in the logging array is a single-key object mapping a function name
prefix to a log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

If the "firefly" AppConfig application does not yet exist it is bootstrapped
(application + environment + logging profile) before the configuration is written.

A new hosted configuration version is created and immediately deployed using
the AllAtOnce deployment strategy.
"""

import json
import logging
import os
import time

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

appconfig = boto3.client("appconfig")
SUPER_GROUP = "super_users"
ENVIRONMENT_NAME = os.environ["ENVIRONMENT_NAME"]
APP_NAME = "firefly"
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


def _find_or_create_firefly_app():
    """Return (app_id, env_id, profile_id), creating the application if it does not exist."""
    # Try to find the existing application
    paginator = appconfig.get_paginator("list_applications")
    for page in paginator.paginate():
        for app in page.get("Items", []):
            if app["Name"] == APP_NAME:
                app_id = app["Id"]

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
                    env_resp = appconfig.create_environment(
                        ApplicationId=app_id,
                        Name=ENVIRONMENT_NAME,
                    )
                    env_id = env_resp["Id"]

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
                    profile_resp = appconfig.create_configuration_profile(
                        ApplicationId=app_id,
                        Name=PROFILE_NAME,
                        LocationUri="hosted",
                        Type="AWS.Freeform",
                    )
                    profile_id = profile_resp["Id"]

                return app_id, env_id, profile_id

    # Application does not exist — bootstrap it
    app_resp = appconfig.create_application(Name=APP_NAME)
    app_id = app_resp["Id"]

    env_resp = appconfig.create_environment(
        ApplicationId=app_id,
        Name=ENVIRONMENT_NAME,
    )
    env_id = env_resp["Id"]

    profile_resp = appconfig.create_configuration_profile(
        ApplicationId=app_id,
        Name=PROFILE_NAME,
        LocationUri="hosted",
        Type="AWS.Freeform",
    )
    profile_id = profile_resp["Id"]

    return app_id, env_id, profile_id


def lambda_handler(event, context):
    try:
        if not _is_super_user(event):
            return _response(403, {"message": "Forbidden"})

        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _response(400, {"message": "Invalid JSON body"})

        logging_config = body.get("logging")
        if logging_config is None:
            return _response(400, {"message": "Missing required field: logging"})
        if not isinstance(logging_config, list):
            return _response(400, {"message": "Field 'logging' must be an array"})

        for i, entry in enumerate(logging_config):
            if not isinstance(entry, dict) or len(entry) != 1:
                return _response(400, {"message": f"logging[{i}] must be a single-key object"})
            level = next(iter(entry.values())).upper()
            if level not in VALID_LEVELS:
                return _response(400, {"message": f"logging[{i}] has invalid level '{level}'; must be one of {sorted(VALID_LEVELS)}"})

        normalized = [{k: v.upper()} for entry in logging_config for k, v in entry.items()]

        app_id, env_id, profile_id = _find_or_create_firefly_app()

        content_bytes = json.dumps(normalized).encode("utf-8")
        ver_resp = appconfig.create_hosted_configuration_version(
            ApplicationId=app_id,
            ConfigurationProfileId=profile_id,
            Content=content_bytes,
            ContentType="application/json",
        )
        version_number = ver_resp["VersionNumber"]

        for attempt in range(10):
            try:
                appconfig.start_deployment(
                    ApplicationId=app_id,
                    EnvironmentId=env_id,
                    DeploymentStrategyId=DEPLOYMENT_STRATEGY,
                    ConfigurationProfileId=profile_id,
                    ConfigurationVersion=str(version_number),
                )
                break
            except ClientError as e:
                if e.response["Error"]["Code"] == "ConflictException" and attempt < 9:
                    time.sleep(2)
                    continue
                raise

        return _response(200, {
            "version": version_number,
            "logging": normalized,
        })

    except ClientError as e:
        logger.exception("AWS ClientError")
        return _response(500, {"message": str(e)})
    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
