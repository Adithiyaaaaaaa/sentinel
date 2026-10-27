import json
import logging
from datetime import UTC, datetime


class MetadataFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {"time": datetime.now(UTC).isoformat(), "level": record.levelname, "event": record.getMessage()}
        for key in ("scan_id", "duration_ms", "file_count", "error_type"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        return json.dumps(data)


def configure_logging() -> None:
    logger = logging.getLogger("sentinel")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(MetadataFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
