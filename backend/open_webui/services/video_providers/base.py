"""Provider-neutral contract. IDs/URLs from providers never become public paths."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class ProviderError(Exception):
    """Only safe, user-facing messages; never include raw vendor responses."""


class SubmissionUnknown(ProviderError):
    pass


class VideoProvider(ABC):
    capabilities: dict[str, Any]

    def __init__(self, config):
        self.config = config

    @abstractmethod
    async def prepare_asset(self, path: Path, media_type: str) -> str:
        """One asset per call so the caller can immediately persist the result."""

    @abstractmethod
    async def submit(self, request: dict, assets: dict) -> str:
        """Return external ID; ambiguous acceptance MUST raise SubmissionUnknown."""

    @abstractmethod
    async def poll(self, external_id: str) -> dict:
        """Return state=pending|processing|completed|failed and optional result_url."""

    @abstractmethod
    async def fetch_result(self, result: dict, destination: Path) -> None:
        """Stream artifact to destination; do not persist temporary signed URLs."""
