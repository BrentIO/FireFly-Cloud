"""
POST /appconfig — create a new AppConfig application with a logging configuration profile.

Requires the caller to be in the super_users group.

Request body:
  {
    "name": "firefly-func-my-app",
    "logging": [{"prefix": "LEVEL"}, ...]
  }

Creates the application, an environment matching ENVIRONMENT_NAME, a 'logging'
configuration profile, an initial hosted configuration version, and immediately
deploys it using the AllAtOnce deployment strategy.

Returns 409 if an application with the given name already exists.
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


def _app_exists(name):
    """Return True if an AppConfig application with this name already exists."""
    paginator = appconfig.get_paginator("list_applications")
    for page in paginator.paginate():
        for app in page.get("Items", []):
            if app["Name"] == name:
                return True
    return False


def lambda_handler(event, context):
    try:
        if not _is_super_user(event):
            return _response(403, {"message": "Forbidden"})

        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _response(400, {"message": "Invalid JSON body"})

        name = (body.get("name") or "").strip()
        if not name:
            return _response(400, {"message": "Missing required field: name"})

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

        if _app_exists(name):
            return _response(409, {"message": f"Application '{name}' already exists"})

        # Create application
        app_resp = appconfig.create_application(Name=name)
        app_id = app_resp["Id"]

        # Create environment
        env_resp = appconfig.create_environment(
            ApplicationId=app_id,
            Name=ENVIRONMENT_NAME,
        )
        env_id = env_resp["Id"]

        # Create logging configuration profile
        profile_resp = appconfig.create_configuration_profile(
            ApplicationId=app_id,
            Name=PROFILE_NAME,
            LocationUri="hosted",
            Type="AWS.Freeform",
        )
        profile_id = profile_resp["Id"]

        # Create initial hosted configuration version
        content_bytes = json.dumps(normalized).encode("utf-8")
        ver_resp = appconfig.create_hosted_configuration_version(
            ApplicationId=app_id,
            ConfigurationProfileId=profile_id,
            Content=content_bytes,
            ContentType="application/json",
        )
        version_number = ver_resp["VersionNumber"]

        # Deploy immediately; retry if a deployment is already in progress
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

        return _response(201, {
            "name": name,
            "version": version_number,
            "logging": normalized,
        })

    except ClientError as e:
        logger.exception("AWS ClientError")
        return _response(500, {"message": str(e)})
    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
