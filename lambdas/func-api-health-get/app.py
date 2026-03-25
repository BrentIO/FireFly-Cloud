from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
import json

logging_config = get_appconfig(profile="logging")
logger = configure_logger(logging_config)


def health(event, context):
    logger.debug("GET /health")
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"status": "OK"}, indent=4)
    }
