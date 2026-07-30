"""Bounded album-art cache for the Pi renderer."""

from __future__ import annotations

import logging
from collections import OrderedDict

import numpy as np
from numpy.typing import NDArray

from shared.models import AssetMetadata
from shared.protocol import AssetFrame

LOGGER = logging.getLogger(__name__)


class AssetCache:
    """Keeps a small number of host-prepared RGB565 album-art frames."""

    def __init__(self, *, capacity: int = 8) -> None:
        if capacity <= 0:
            raise ValueError("asset cache capacity must be positive")
        self.capacity = capacity
        self._entries: OrderedDict[str, tuple[AssetMetadata, NDArray[np.uint16]]] = OrderedDict()
        self.revision = 0

    def store(self, frame: AssetFrame) -> bool:
        metadata = frame.metadata
        if metadata.media_type != "image/rgb565":
            LOGGER.warning("Ignoring unsupported asset media type %s", metadata.media_type)
            return False
        if metadata.width is None or metadata.height is None:
            LOGGER.warning("Ignoring RGB565 asset without dimensions")
            return False
        expected = metadata.width * metadata.height * 2
        if len(frame.data) != expected:
            LOGGER.warning(
                "Ignoring RGB565 asset with unexpected size bytes=%d expected=%d",
                len(frame.data),
                expected,
            )
            return False
        pixels = np.frombuffer(frame.data, dtype="<u2").reshape(metadata.height, metadata.width)
        self._entries[metadata.asset_id] = (metadata, pixels.copy())
        self._entries.move_to_end(metadata.asset_id)
        while len(self._entries) > self.capacity:
            self._entries.popitem(last=False)
        self.revision += 1
        LOGGER.info(
            "Cached album art id=%s size=%dx%d",
            metadata.asset_id,
            metadata.width,
            metadata.height,
        )
        return True

    def get_rgb565(self, asset_id: str | None) -> NDArray[np.uint16] | None:
        if asset_id is None:
            return None
        entry = self._entries.get(asset_id)
        if entry is None:
            return None
        self._entries.move_to_end(asset_id)
        return entry[1]

    def __contains__(self, asset_id: object) -> bool:
        return isinstance(asset_id, str) and asset_id in self._entries
