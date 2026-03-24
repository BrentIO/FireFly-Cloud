import logging
import os
import json

VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class _json_formatter(logging.Formatter):
    """Formats logs as JSON including any extra fields and stack trace."""

    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include any extra fields
        for key, value in record.__dict__.items():
            if key not in log_record and key not in (
                "args", "msg", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text",
                "stack_info", "lineno", "funcName", "created",
                "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process"
            ):
                log_record[key] = value

        # Include stack trace if present
        if record.exc_info:
            log_record["stack"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


def configure_logger(config: dict):
    """
    Returns a logger for the current function using the AppConfig logging setting.

    Config format: {"logging": "WARNING"}
    Falls back to WARNING if not configured or if the level is unrecognised.
    """
    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "")

    level_name = "WARNING"
    if isinstance(config, dict):
        raw = config.get("logging", "WARNING")
        if isinstance(raw, str) and raw.upper() in VALID_LEVELS:
            level_name = raw.upper()

    numeric = getattr(logging, level_name, logging.WARNING)

    logger = logging.getLogger(function_name)
    logger.setLevel(numeric)

    # Only add a handler if none exist
    if not logger.hasHandlers():
        handler = logging.StreamHandler()
        handler.setFormatter(_json_formatter())
        logger.addHandler(handler)

    return logger


__all__ = ["configure_logger"]
