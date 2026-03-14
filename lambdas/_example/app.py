from shared.app_config import get_appconfig
from shared.logging_config import configure_logger
from shared.feature_flags import is_enabled

def handler(event, context):
    try:
        # Fetch configs once
        logging_config = get_appconfig(profile="logging")
        feature_config = get_appconfig(profile="features")

        # Configure logger
        logger = configure_logger(logging_config)

        # Logging demonstration
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message", extra={"foo":"bar"})
        logger.error("Error message")

        # Feature flag example
        if is_enabled("foo", feature_config):
            logger.info("Feature foo is enabled")

        # Example return
        return True
    
    except Exception:
        logger.exception(
            "Unhandled exception",
            extra={"foo": "bar"}
        )
        raise