import json
import logging


class RequestJsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "user_id": getattr(record, "user_id", None),
            "landlord_id": getattr(record, "landlord_id", None),
        }
        return json.dumps(payload)
