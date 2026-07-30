"""Host-side album art preparation for the RGB565 companion display."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

from shared.models import AssetMetadata

ALBUM_ART_SIZE = 152


@dataclass(frozen=True, slots=True)
class PreparedAlbumArt:
    metadata: AssetMetadata
    data: bytes


def pack_rgb565_image(pixels: np.ndarray) -> bytes:
    """Pack an HxWx3 uint8 RGB image into little-endian RGB565 bytes."""

    if pixels.ndim != 3 or pixels.shape[2] != 3:
        raise ValueError("pixels must have shape (height, width, 3)")
    red = (pixels[:, :, 0].astype(np.uint16) & 0xF8) << 8
    green = (pixels[:, :, 1].astype(np.uint16) & 0xFC) << 3
    blue = pixels[:, :, 2].astype(np.uint16) >> 3
    return (red | green | blue).astype("<u2").tobytes()


def prepare_album_art(image_bytes: bytes, *, size: int = ALBUM_ART_SIZE) -> PreparedAlbumArt:
    """Resize album art on the host and emit display-ready RGB565 bytes."""

    if size <= 0:
        raise ValueError("album art size must be positive")
    with Image.open(io.BytesIO(image_bytes)) as image:
        fitted = ImageOps.fit(
            image.convert("RGB"),
            (size, size),
            method=Image.Resampling.LANCZOS,
        )
    pixels = np.asarray(fitted, dtype=np.uint8)
    data = pack_rgb565_image(pixels)
    digest = hashlib.sha256(data).hexdigest()
    metadata = AssetMetadata(
        asset_id=f"album-{digest[:16]}",
        sha256=digest,
        media_type="image/rgb565",
        byte_length=len(data),
        width=size,
        height=size,
    )
    return PreparedAlbumArt(metadata=metadata, data=data)
