import logging
import os
from datetime import datetime, timedelta, timezone
from logging.config import dictConfig

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)


class TZFormatter(logging.Formatter):
    def __init__(self, *args, **kwargs):
        self.tz_offset = int(os.getenv("TZ_OFFSET", "9"))
        super().__init__(*args, **kwargs)

    def formatTime(self, record, datefmt=None):
        tz = timezone(timedelta(hours=self.tz_offset))
        dt = datetime.fromtimestamp(record.created, tz)
        return dt.strftime(datefmt or self.default_time_format)


class IgnorePathsFilter(logging.Filter):
    """
    Filter remove access log, example /metrics, /healthcheck
    """
    def __init__(self, ignored_paths=None):
        super().__init__()
        self.ignored_paths = ignored_paths or []

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(path in msg for path in self.ignored_paths)


def setup_logging(service_name: str, ignored_paths: list):
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    env = os.getenv("ENV", "local").lower()
    log_file = os.path.join(LOGS_DIR, f"{service_name}-{env}.log")

    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,

        "formatters": {
            "default": {
                "()": TZFormatter,
                "format": "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "()": TZFormatter,
                "format": "[%(asctime)s] [%(levelname)s] %(name)s | %(filename)s:%(lineno)d | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },

        "filters": {
            "ignore_paths": {
                "()": "config.log.IgnorePathsFilter",
                "ignored_paths": ignored_paths
            }
        },

        "handlers": {
            "file": {
                "class": "logging.FileHandler",
                "filename": log_file,
                "formatter": "detailed",
                "encoding": "utf-8",
                "filters": ["ignore_paths"],
            },
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
                "filters": ["ignore_paths"],
            },
        },

        "loggers": {
            "uvicorn.access": {
                "handlers": ["file", "console"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["file", "console"],
                "level": "INFO",
                "propagate": False,
            },
            # LiteLLM can emit repetitive provider-list/info logs.
            # Keep it at WARNING to reduce container log noise.
            "LiteLLM": {
                "handlers": ["file", "console"],
                "level": "WARNING",
                "propagate": False,
            },
            "litellm": {
                "handlers": ["file", "console"],
                "level": "WARNING",
                "propagate": False,
            },
        },

        "root": {
            "handlers": ["file", "console"],
            "level": log_level,
        }
    })
