import logging
import os
import json

def _get_function_name():
    return os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "")


def _get_log_level(function_name: str, config_json: dict):
    observed = logging.WARNING

    for entry in config_json:
        for key, val in entry.items():
            if function_name.startswith(key):
                level_name = val.upper()
                numeric_level = getattr(logging, level_name, None)
                if isinstance(numeric_level, int):
                    observed = min(observed, numeric_level)

    return observed


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


def configure_logger(logging_config: dict):
    """
    Returns a logger for the current function using AWS AppConfig logging settings.

    Example Configuration:
    ```json
    [
        {"firefly-func-s3": "INFO"},
        {"dynamodb": "DEBUG"},
        {"firefly-func-s3-example": "DEBUG"}
    ]
    ```
    """
    function_name = _get_function_name()
    observed = _get_log_level(function_name, logging_config)

    logger = logging.getLogger(function_name)
    logger.setLevel(observed)

    # Only add a handler if none exist
    if not logger.hasHandlers():
        handler = logging.StreamHandler()
        handler.setFormatter(_json_formatter())
        logger.addHandler(handler)

    return logger


__all__ = ["configure_logger"]
