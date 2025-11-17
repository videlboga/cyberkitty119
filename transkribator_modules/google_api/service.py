"""Helpers to build Google API service clients."""

from functools import lru_cache

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from transkribator_modules.config import logger


@lru_cache(maxsize=4)
def _discovery_cache(service_name: str, version: str):
    return (service_name, version)


def build_service(service_name: str, version: str, credentials):
    try:
        return build(
            serviceName=service_name,
            version=version,
            credentials=credentials,
            cache_discovery=False,
        )
    except HttpError as exc:
        logger.error(
            "Failed to build Google service",
            extra={"service": service_name, "error": str(exc)},
        )
        raise
