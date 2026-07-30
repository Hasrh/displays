"""Album art preparation and Pi asset cache tests."""

from __future__ import annotations

import hashlib
import io

import numpy as np
from PIL import Image

from pc.assets import ALBUM_ART_SIZE, prepare_album_art
from pi.assets import AssetCache
from pi.canvas import RGB565Canvas
from shared.models import AssetMetadata
from shared.protocol import AssetFrame, decode_asset_frame, encode_asset_frame


def _jpeg_bytes(color: tuple[int, int, int] = (200, 40, 80), size: int = 64) -> bytes:
    image = Image.new("RGB", (size, size), color)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_prepare_album_art_emits_rgb565_metadata() -> None:
    prepared = prepare_album_art(_jpeg_bytes())
    assert prepared.metadata.media_type == "image/rgb565"
    assert prepared.metadata.width == ALBUM_ART_SIZE
    assert prepared.metadata.height == ALBUM_ART_SIZE
    assert prepared.metadata.byte_length == ALBUM_ART_SIZE * ALBUM_ART_SIZE * 2
    assert len(prepared.data) == prepared.metadata.byte_length
    assert prepared.metadata.asset_id.startswith("album-")


def test_asset_cache_stores_and_evicts_rgb565_frames() -> None:
    first = prepare_album_art(_jpeg_bytes((10, 20, 30)))
    second = prepare_album_art(_jpeg_bytes((40, 50, 60)))
    frame_one = decode_asset_frame(encode_asset_frame(first.metadata, first.data))
    frame_two = decode_asset_frame(encode_asset_frame(second.metadata, second.data))
    cache = AssetCache(capacity=1)
    assert cache.store(frame_one)
    assert first.metadata.asset_id in cache
    assert cache.store(frame_two)
    assert first.metadata.asset_id not in cache
    assert second.metadata.asset_id in cache
    pixels = cache.get_rgb565(second.metadata.asset_id)
    assert pixels is not None
    assert pixels.shape == (ALBUM_ART_SIZE, ALBUM_ART_SIZE)


def test_canvas_blit_rgb565_clips() -> None:
    canvas = RGB565Canvas(4, 4)
    canvas.clear((0, 0, 0))
    source = np.full((3, 3), 0xF800, dtype="<u2")
    canvas.blit_rgb565(-1, -1, source)
    frame = bytes(canvas.frame())
    assert frame[0:2] == b"\x00\xf8"
    assert frame[2:4] == b"\x00\xf8"


def test_asset_cache_rejects_non_rgb565() -> None:
    data = b"jpeg"
    metadata = AssetMetadata(
        asset_id="jpeg-1",
        sha256=hashlib.sha256(data).hexdigest(),
        media_type="image/jpeg",
        byte_length=len(data),
    )
    cache = AssetCache()
    assert cache.store(AssetFrame(metadata=metadata, data=data)) is False
