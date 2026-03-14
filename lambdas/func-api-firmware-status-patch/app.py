from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import json
import boto3
import os

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
        product_id = path_params.get("product_id")
        version = path_params.get("version")

        body = json.loads(event.get("body") or "{}")
        new_status = body.get("release_status")

        if not new_status:
            return _response(400, {"message": "Missing required field: release_status"})

        logger.debug(f"PATCH status for product_id='{product_id}' version='{version}' new_status='{new_status}'")

        response = firmware_table.get_item(
            Key={"product_id": product_id, "version": version}
        )
        item = response.get("Item")
        if not item:
            return _response(404, {"message": f"Firmware not found: {product_id}/{version}"})

        current_status = item.get("release_status")
        allowed = VALID_TRANSITIONS.get(current_status, [])

        if new_status not in allowed:
            return _response(422, {
                "message": f"Cannot transition from '{current_status}' to '{new_status}'",
                "current_status": current_status,
                "allowed_transitions": allowed,
            })

        firmware_table.update_item(
            Key={"product_id": product_id, "version": version},
            UpdateExpression="SET release_status = :rs",
            ExpressionAttributeValues={":rs": new_status},
        )

        logger.debug(f"Transitioned product_id='{product_id}' version='{version}' from '{current_status}' to '{new_status}'")

        item["release_status"] = new_status
        return _response(200, item)

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "Internal server error"})
