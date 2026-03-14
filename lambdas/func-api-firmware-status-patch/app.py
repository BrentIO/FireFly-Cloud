from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import json
import boto3
import os
from boto3.dynamodb.conditions import Attr

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

dynamodb = boto3.resource("dynamodb", endpoint_url=os.environ.get("DYNAMODB_ENDPOINT"))

TABLE_NAME = os.environ["DYNAMODB_FIRMWARE_TABLE_NAME"]
firmware_table = dynamodb.Table(TABLE_NAME)

VALID_TRANSITIONS = {
    "READY_TO_TEST": ["TESTING"],
    "TESTING": ["RELEASED"],
    "RELEASED": ["REVOKED"],
}


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, indent=4, default=str),
    }


def lambda_handler(event, context):
    try:
        path_params = event.get("pathParameters") or {}
        zip_name = path_params.get("zip_name")

        body = json.loads(event.get("body") or "{}")
        new_status = body.get("release_status")

        if not new_status:
            return _response(400, {"message": "Missing required field: release_status"})

        logger.debug(f"PATCH status for zip_name='{zip_name}' new_status='{new_status}'")

        # zip_name (UUID) is the unique identifier for a specific build.
        # Scan is used because zip_name is not the DynamoDB primary key.
        response = firmware_table.scan(
            FilterExpression=Attr("zip_name").eq(zip_name)
        )
        items = response.get("Items", [])
        if not items:
            return _response(404, {"message": f"Firmware not found: {zip_name}"})

        item = items[0]
        product_id = item["product_id"]
        version = item["version"]
        current_status = item.get("release_status")
        allowed = VALID_TRANSITIONS.get(current_status, [])

        if new_status not in allowed:
            return _response(422, {
                "message": f"Cannot transition from '{current_status}' to '{new_status}'",
                "current_status": current_status,
                "allowed_transitions": allowed,
            })

        # UpdateItem uses the DynamoDB primary key (product_id, version)
        firmware_table.update_item(
            Key={"product_id": product_id, "version": version},
            UpdateExpression="SET release_status = :rs",
            ExpressionAttributeValues={":rs": new_status},
        )

        logger.debug(f"Transitioned zip_name='{zip_name}' from '{current_status}' to '{new_status}'")

        item["release_status"] = new_status
        return _response(200, item)

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
