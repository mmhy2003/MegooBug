import logging
import sys

from app.config import settings


def setup_logging() -> logging.Logger:
    """Configure application-wide logging.

    - Development: colored, human-readable format
    - Production: JSON-structured format for log aggregation
    """
    log_level = logging.DEBUG if settings.ENVIRONMENT == "development" else logging.INFO

    # Root logger config
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s │ %(levelname)-8s │ %(name)-20s │ %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    # Suppress noisy third-party loggers
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.WARNING if settings.ENVIRONMENT == "production" else logging.INFO
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    logger = logging.getLogger("megoobug")
    logger.setLevel(log_level)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the 'megoobug' namespace.

    Usage:
        from app.logging import get_logger
        logger = get_logger(__name__)
        logger.info("Something happened")
    """
    return logging.getLogger(f"megoobug.{name}")
