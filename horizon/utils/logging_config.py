"""
Centralized logging configuration for the Horizon pipeline.

Provides consistent logging setup across all modules with:
- File and console logging
- Configurable log levels
- Structured log format with timestamps and module names
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional


def setup_logging(
    log_level: int = logging.INFO,
    log_file: Optional[Path] = None,
    log_dir: Path = Path("logs"),
) -> logging.Logger:
    """
    Configure logging for the entire Horizon pipeline.

    Args:
        log_level: Logging level (logging.DEBUG, logging.INFO, etc.)
        log_file: Path to log file. If None, defaults to logs/horizon.log
        log_dir: Directory to store log files

    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    log_dir.mkdir(exist_ok=True)

    if log_file is None:
        log_file = log_dir / "horizon.log"

    # Get root logger
    logger = logging.getLogger("horizon")
    logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Log format
    log_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler (logs everything)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10485760, backupCount=5  # 10MB per file, keep 5 backups
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

    # Console handler (only logs INFO and above)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    Args:
        name: Module name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(f"horizon.{name}")
