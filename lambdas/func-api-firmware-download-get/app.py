from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import json
import boto3
import os
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)

dynamodb = boto3.resource("dynamodb", endpoint_url=os.environ.get("DYNAMODB_ENDPOINT"))
s3 = boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT"))

TABLE_NAME = os.environ["DYNAMODB_FIRMWARE_TABLE_NAME"]
S3_FIRMWARE_PRIVATE_BUCKET_NAME = os.environ["S3_FIRMWARE_PRIVATE_BUCKET_NAME"]

firmware_table = dynamodb.Table(TABLE_NAME)

PRESIGNED_URL_EXPIRY_SECONDS = 900  # 15 minutes


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

        logger.debug(f"GET /firmware/{zip_name}/download")

        response = firmware_table.query(
            IndexName="zip_name-index",
            KeyConditionExpression=Key("zip_name").eq(zip_name)
        )
        items = response.get("Items", [])

        if not items:
            return _response(404, {"message": f"Firmware not found: {zip_name}"})

        item = items[0]
        current_status = item.get("release_status")

        if current_status == "DELETED":
            return _response(410, {"message": "Firmware has been deleted"})

        if current_status == "PROCESSING":
            return _response(409, {"message": "Firmware is still being processed"})

        prefix = "errors/" if current_status == "ERROR" else "processed/"
        s3_key = f"{prefix}{zip_name}"

        try:
            s3.head_object(Bucket=S3_FIRMWARE_PRIVATE_BUCKET_NAME, Key=s3_key)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey"):
                logger.error(f"Firmware file not found in storage: bucket='{S3_FIRMWARE_PRIVATE_BUCKET_NAME}' key='{s3_key}'")
                return _response(500, {"message": "A service exception occurred, please check the service logs for more detail."})
            logger.exception(f"Service error checking firmware file: bucket='{S3_FIRMWARE_PRIVATE_BUCKET_NAME}' key='{s3_key}'")
            return _response(500, {"message": "A service exception occurred, please check the service logs for more detail."})

        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_FIRMWARE_PRIVATE_BUCKET_NAME, "Key": s3_key},
            ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
        )

        logger.debug(f"Generated pre-signed URL for zip_name='{zip_name}' key='{s3_key}' expiry={PRESIGNED_URL_EXPIRY_SECONDS}s")

        return _response(200, {
            "url": url,
            "expires_in": PRESIGNED_URL_EXPIRY_SECONDS,
        })

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"message": "A service exception occurred, please check the service logs for more detail."})
