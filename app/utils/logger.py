import structlog
import logging
import os


def get_logger(name: str):
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, log_level))
    return structlog.get_logger(name)
