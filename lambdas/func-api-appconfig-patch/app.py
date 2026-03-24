"""
PATCH /appconfig/{function_name}       — create or update the AppConfig for a Lambda function.
POST  /appconfig/{function_name}/deploy — deploy the latest staged version to the current environment.

Both routes require the caller to be in the super_users group.

PATCH request body:
  {"logging": "WARNING"}
  Additional keys are accepted and stored for future feature-flag use.

PATCH response (200):
  {"name": "firefly-func-api-firmware-get", "logging": "WARNING", "version": 3}

PATCH creates a new hosted configuration version but does NOT deploy it.
Call POST /appconfig/{function_name}/deploy to activate the change.

POST /deploy response (200):
  {"name": "firefly-func-api-firmware-get", "version": 3, "environment": "dev", "status": "DEPLOYING"}
"""

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

appconfig = boto3.client("appconfig")
lambda_client = boto3.client("lambda")

SUPER_GROUP = "super_users"
ENVIRONMENT_NAME = os.environ["ENVIRONMENT_NAME"]
PROFILE_NAME = "logging"
FUNCTION_PREFIX = "firefly-func-"
VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
DEPLOYMENT_STRATEGY = "AppConfig.AllAtOnce"


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


def _function_exists(function_name):
    try:
        lambda_client.get_function(FunctionName=function_name)
        return True
    except ClientError:
        return False


def _find_or_create_app(function_name):
    """Return (app_id, env_id, profile_id), creating any missing resources."""
    app_id = None
    paginator = appconfig.get_paginator("list_applications")
    for page in paginator.paginate():
        for app in page.get("Items", []):
            if app["Name"] == function_name:
                app_id = app["Id"]
                break
        if app_id:
            break

    if not app_id:
        resp = appconfig.create_application(Name=function_name)
        app_id = resp["Id"]

    env_id = None
    env_paginator = appconfig.get_paginator("list_environments")
    for page in env_paginator.paginate(ApplicationId=app_id):
        for env in page.get("Items", []):
            if env["Name"] == ENVIRONMENT_NAME:
                env_id = env["Id"]
                break
        if env_id:
            break

    if not env_id:
        resp = appconfig.create_environment(ApplicationId=app_id, Name=ENVIRONMENT_NAME)
        env_id = resp["Id"]

    profile_id = None
    profile_paginator = appconfig.get_paginator("list_configuration_profiles")
    for page in profile_paginator.paginate(ApplicationId=app_id):
        for profile in page.get("Items", []):
            if profile["Name"] == PROFILE_NAME:
                profile_id = profile["Id"]
                break
        if profile_id:
            break

    if not profile_id:
        resp = appconfig.create_configuration_profile(
            ApplicationId=app_id,
            Name=PROFILE_NAME,
            LocationUri="hosted",
            Type="AWS.Freeform",
        )
        profile_id = resp["Id"]

    return app_id, env_id, profile_id


def _find_app(function_name):
    """Return (app_id, env_id, profile_id) or None if the application does not exist."""
    app_id = None
    paginator = appconfig.get_paginator("list_applications")
    for page in paginator.paginate():
        for app in page.get("Items", []):
            if app["Name"] == function_name:
                app_id = app["Id"]
                break
        if app_id:
            break

    if not app_id:
        return None

    env_id = None
    env_paginator = appconfig.get_paginator("list_environments")
    for page in env_paginator.paginate(ApplicationId=app_id):
        for env in page.get("Items", []):
            if env["Name"] == ENVIRONMENT_NAME:
                env_id = env["Id"]
                break
        if env_id:
            break

    if not env_id:
        return None

    profile_id = None
    profile_paginator = appconfig.get_paginator("list_configuration_profiles")
    for page in profile_paginator.paginate(ApplicationId=app_id):
        for profile in page.get("Items", []):
            if profile["Name"] == PROFILE_NAME:
                profile_id = profile["Id"]
                break
        if profile_id:
            break

    if not profile_id:
        return None

    return app_id, env_id, profile_id


def _handle_patch(event, function_name):
    if not function_name.startswith(FUNCTION_PREFIX):
        return _response(400, {"message": f"Function name must start with '{FUNCTION_PREFIX}'"})

    if not _function_exists(function_name):
        return _response(404, {"message": f"Lambda function '{function_name}' not found"})

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"message": "Invalid JSON body"})

    if "logging" not in body:
        return _response(400, {"message": "Missing required field: logging"})

    level = str(body["logging"]).upper()
    if level not in VALID_LEVELS:
        return _response(400, {"message": f"Invalid log level '{level}'; must be one of {sorted(VALID_LEVELS)}"})

    app_id, env_id, profile_id = _find_or_create_app(function_name)

    # Build config — logging is normalised; any other keys are passed through for future use
    config = {k: v for k, v in body.items() if k != "logging"}
    config["logging"] = level

    ver_resp = appconfig.create_hosted_configuration_version(
        ApplicationId=app_id,
        ConfigurationProfileId=profile_id,
        Content=json.dumps(config).encode("utf-8"),
        ContentType="application/json",
    )

    return _response(200, {
        "name": function_name,
        "logging": level,
        "version": ver_resp["VersionNumber"],
    })


def _handle_deploy(function_name):
    if not function_name.startswith(FUNCTION_PREFIX):
        return _response(400, {"message": f"Function name must start with '{FUNCTION_PREFIX}'"})

    result = _find_app(function_name)
    if result is None:
        return _response(404, {"message": f"No AppConfig application found for '{function_name}'. Use PATCH to create one first."})

    app_id, env_id, profile_id = result

    versions_resp = appconfig.list_hosted_configuration_versions(
        ApplicationId=app_id,
        ConfigurationProfileId=profile_id,
        MaxResults=1,
    )
    versions = versions_resp.get("Items", [])
    if not versions:
        return _response(404, {"message": "No configuration version found. Use PATCH to create one first."})

    latest_version = versions[0]["VersionNumber"]

    deploy_resp = appconfig.start_deployment(
        ApplicationId=app_id,
        EnvironmentId=env_id,
        DeploymentStrategyId=DEPLOYMENT_STRATEGY,
        ConfigurationProfileId=profile_id,
        ConfigurationVersion=str(latest_version),
    )

    return _response(200, {
        "name": function_name,
        "version": latest_version,
        "environment": ENVIRONMENT_NAME,
        "status": deploy_resp.get("State", "DEPLOYING"),
    })


def lambda_handler(event, context):
    try:
        if not _is_super_user(event):
            return _response(403, {"message": "Forbidden"})

        route_key = event.get("routeKey", "")
        path_params = event.get("pathParameters") or {}
        function_name = path_params.get("function_name", "")

        if route_key.startswith("PATCH "):
            return _handle_patch(event, function_name)
        elif route_key.startswith("POST "):
            return _handle_deploy(function_name)
        else:
            return _response(404, {"message": "Not found"})

    except ClientError as e:
        logger.exception("AWS ClientError")
        return _response(500, {"message": str(e)})
    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
