"""Immutable domain models shared by the host and Raspberry Pi."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, TypeAlias

from shared.constants import FFT_BIN_COUNT, MAX_ASSET_BYTES

SequenceNumber: TypeAlias = int
MessageId: TypeAlias = str
JsonObject: TypeAlias = dict[str, Any]


def _number(value: object, field: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    if minimum is not None and number < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return number


def _optional_number(
    value: object,
    field: str,
    *,
    minimum: float | None = None,
) -> float | None:
    if value is None:
        return None
    return _number(value, field, minimum=minimum)


def _percentage(value: object, field: str) -> float:
    number = _number(value, field, minimum=0.0)
    if number > 100.0:
        raise ValueError(f"{field} must not exceed 100")
    return number


def _optional_percentage(value: object, field: str) -> float | None:
    if value is None:
        return None
    return _percentage(value, field)


def _string(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        qualifier = "a string" if allow_empty else "a non-empty string"
        raise ValueError(f"{field} must be {qualifier}")
    return value


def _optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _string(value, field)


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _object(value: object, field: str) -> JsonObject:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object with string keys")
    return value


@dataclass(frozen=True, slots=True)
class MediaState:
    title: str
    artist: str
    album: str | None
    is_playing: bool
    position_seconds: float
    duration_seconds: float
    volume_percent: float | None = None
    album_art_id: str | None = None

    @classmethod
    def from_dict(cls, value: object) -> MediaState:
        data = _object(value, "media")
        position = _number(data.get("position_seconds"), "media.position_seconds", minimum=0.0)
        duration = _number(data.get("duration_seconds"), "media.duration_seconds", minimum=0.0)
        if duration and position > duration:
            position = duration
        return cls(
            title=_string(data.get("title"), "media.title", allow_empty=True),
            artist=_string(data.get("artist"), "media.artist", allow_empty=True),
            album=_optional_string(data.get("album"), "media.album"),
            is_playing=_boolean(data.get("is_playing"), "media.is_playing"),
            position_seconds=position,
            duration_seconds=duration,
            volume_percent=_optional_percentage(data.get("volume_percent"), "media.volume_percent"),
            album_art_id=_optional_string(data.get("album_art_id"), "media.album_art_id"),
        )

    def to_dict(self) -> JsonObject:
        return {
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "is_playing": self.is_playing,
            "position_seconds": self.position_seconds,
            "duration_seconds": self.duration_seconds,
            "volume_percent": self.volume_percent,
            "album_art_id": self.album_art_id,
        }


@dataclass(frozen=True, slots=True)
class GpuMetrics:
    name: str
    usage_percent: float | None = None
    vram_usage_percent: float | None = None
    temperature_c: float | None = None

    @classmethod
    def from_dict(cls, value: object) -> GpuMetrics:
        data = _object(value, "gpu")
        return cls(
            name=_string(data.get("name"), "gpu.name"),
            usage_percent=_optional_percentage(data.get("usage_percent"), "gpu.usage_percent"),
            vram_usage_percent=_optional_percentage(
                data.get("vram_usage_percent"), "gpu.vram_usage_percent"
            ),
            temperature_c=_optional_number(data.get("temperature_c"), "gpu.temperature_c"),
        )

    def to_dict(self) -> JsonObject:
        return {
            "name": self.name,
            "usage_percent": self.usage_percent,
            "vram_usage_percent": self.vram_usage_percent,
            "temperature_c": self.temperature_c,
        }


@dataclass(frozen=True, slots=True)
class SystemMetrics:
    cpu_usage_percent: float | None = None
    gpu_usage_percent: float | None = None
    ram_usage_percent: float | None = None
    vram_usage_percent: float | None = None
    cpu_temperature_c: float | None = None
    gpu_temperature_c: float | None = None
    gpus: tuple[GpuMetrics, ...] = ()

    @classmethod
    def from_dict(cls, value: object) -> SystemMetrics:
        data = _object(value, "system")
        raw_gpus = data.get("gpus", [])
        if not isinstance(raw_gpus, list):
            raise ValueError("system.gpus must be an array")
        return cls(
            cpu_usage_percent=_optional_percentage(
                data.get("cpu_usage_percent"), "system.cpu_usage_percent"
            ),
            gpu_usage_percent=_optional_percentage(
                data.get("gpu_usage_percent"), "system.gpu_usage_percent"
            ),
            ram_usage_percent=_optional_percentage(
                data.get("ram_usage_percent"), "system.ram_usage_percent"
            ),
            vram_usage_percent=_optional_percentage(
                data.get("vram_usage_percent"), "system.vram_usage_percent"
            ),
            cpu_temperature_c=_optional_number(
                data.get("cpu_temperature_c"), "system.cpu_temperature_c"
            ),
            gpu_temperature_c=_optional_number(
                data.get("gpu_temperature_c"), "system.gpu_temperature_c"
            ),
            gpus=tuple(GpuMetrics.from_dict(item) for item in raw_gpus),
        )

    def to_dict(self) -> JsonObject:
        return {
            "cpu_usage_percent": self.cpu_usage_percent,
            "gpu_usage_percent": self.gpu_usage_percent,
            "ram_usage_percent": self.ram_usage_percent,
            "vram_usage_percent": self.vram_usage_percent,
            "cpu_temperature_c": self.cpu_temperature_c,
            "gpu_temperature_c": self.gpu_temperature_c,
            "gpus": [gpu.to_dict() for gpu in self.gpus],
        }


@dataclass(frozen=True, slots=True)
class NetworkMetrics:
    download_bytes_per_second: float
    upload_bytes_per_second: float

    @classmethod
    def from_dict(cls, value: object) -> NetworkMetrics:
        data = _object(value, "network")
        return cls(
            download_bytes_per_second=_number(
                data.get("download_bytes_per_second"),
                "network.download_bytes_per_second",
                minimum=0.0,
            ),
            upload_bytes_per_second=_number(
                data.get("upload_bytes_per_second"),
                "network.upload_bytes_per_second",
                minimum=0.0,
            ),
        )

    def to_dict(self) -> JsonObject:
        return {
            "download_bytes_per_second": self.download_bytes_per_second,
            "upload_bytes_per_second": self.upload_bytes_per_second,
        }


@dataclass(frozen=True, slots=True)
class WeatherState:
    temperature_c: float
    condition: str
    observed_at: str
    icon_code: str | None = None

    @classmethod
    def from_dict(cls, value: object) -> WeatherState:
        data = _object(value, "weather")
        return cls(
            temperature_c=_number(data.get("temperature_c"), "weather.temperature_c"),
            condition=_string(data.get("condition"), "weather.condition"),
            observed_at=_string(data.get("observed_at"), "weather.observed_at"),
            icon_code=_optional_string(data.get("icon_code"), "weather.icon_code"),
        )

    def to_dict(self) -> JsonObject:
        return {
            "temperature_c": self.temperature_c,
            "condition": self.condition,
            "observed_at": self.observed_at,
            "icon_code": self.icon_code,
        }


@dataclass(frozen=True, slots=True)
class ClockState:
    time_text: str
    date_text: str

    @classmethod
    def from_dict(cls, value: object) -> ClockState:
        data = _object(value, "clock")
        return cls(
            time_text=_string(data.get("time_text"), "clock.time_text"),
            date_text=_string(data.get("date_text"), "clock.date_text"),
        )

    def to_dict(self) -> JsonObject:
        return {"time_text": self.time_text, "date_text": self.date_text}


@dataclass(frozen=True, slots=True)
class DisplayState:
    media: MediaState | None = None
    system: SystemMetrics | None = None
    network: NetworkMetrics | None = None
    weather: WeatherState | None = None
    clock: ClockState | None = None

    @classmethod
    def from_dict(cls, value: object) -> DisplayState:
        data = _object(value, "state")
        return cls(
            media=MediaState.from_dict(data["media"]) if data.get("media") is not None else None,
            system=(
                SystemMetrics.from_dict(data["system"]) if data.get("system") is not None else None
            ),
            network=(
                NetworkMetrics.from_dict(data["network"])
                if data.get("network") is not None
                else None
            ),
            weather=(
                WeatherState.from_dict(data["weather"]) if data.get("weather") is not None else None
            ),
            clock=ClockState.from_dict(data["clock"]) if data.get("clock") is not None else None,
        )

    def to_dict(self) -> JsonObject:
        return {
            "media": self.media.to_dict() if self.media else None,
            "system": self.system.to_dict() if self.system else None,
            "network": self.network.to_dict() if self.network else None,
            "weather": self.weather.to_dict() if self.weather else None,
            "clock": self.clock.to_dict() if self.clock else None,
        }


@dataclass(frozen=True, slots=True)
class DisplayCapabilities:
    width: int
    height: int
    orientation: int
    target_fps: int
    touch_enabled: bool

    @classmethod
    def from_dict(cls, value: object) -> DisplayCapabilities:
        data = _object(value, "capabilities")
        dimensions: list[int] = []
        for field in ("width", "height", "target_fps"):
            raw = data.get(field)
            if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
                raise ValueError(f"capabilities.{field} must be a positive integer")
            dimensions.append(raw)
        orientation = data.get("orientation")
        if orientation not in {0, 90, 180, 270}:
            raise ValueError("capabilities.orientation must be 0, 90, 180, or 270")
        return cls(
            width=dimensions[0],
            height=dimensions[1],
            orientation=orientation,
            target_fps=dimensions[2],
            touch_enabled=_boolean(data.get("touch_enabled"), "capabilities.touch_enabled"),
        )

    def to_dict(self) -> JsonObject:
        return {
            "width": self.width,
            "height": self.height,
            "orientation": self.orientation,
            "target_fps": self.target_fps,
            "touch_enabled": self.touch_enabled,
        }


@dataclass(frozen=True, slots=True)
class FFTFrame:
    captured_at: str
    bins: tuple[float, ...]

    @classmethod
    def from_dict(cls, value: object) -> FFTFrame:
        data = _object(value, "fft_frame")
        raw_bins = data.get("bins")
        if not isinstance(raw_bins, list) or len(raw_bins) != FFT_BIN_COUNT:
            raise ValueError(f"fft_frame.bins must contain exactly {FFT_BIN_COUNT} values")
        bins = tuple(
            _number(item, f"fft_frame.bins[{index}]", minimum=0.0)
            for index, item in enumerate(raw_bins)
        )
        if any(item > 1.0 for item in bins):
            raise ValueError("fft_frame bins must not exceed 1.0")
        return cls(
            captured_at=_string(data.get("captured_at"), "fft_frame.captured_at"),
            bins=bins,
        )

    def to_dict(self) -> JsonObject:
        return {"captured_at": self.captured_at, "bins": list(self.bins)}


@dataclass(frozen=True, slots=True)
class AssetMetadata:
    asset_id: str
    sha256: str
    media_type: str
    byte_length: int
    width: int | None = None
    height: int | None = None

    @classmethod
    def from_dict(cls, value: object) -> AssetMetadata:
        data = _object(value, "asset")
        sha256 = _string(data.get("sha256"), "asset.sha256").lower()
        if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256):
            raise ValueError("asset.sha256 must be 64 lowercase hexadecimal characters")
        media_type = _string(data.get("media_type"), "asset.media_type").lower()
        if media_type not in {"image/jpeg", "image/webp", "image/rgb565"}:
            raise ValueError("asset.media_type must be image/jpeg, image/webp, or image/rgb565")
        byte_length = data.get("byte_length")
        if (
            isinstance(byte_length, bool)
            or not isinstance(byte_length, int)
            or not 0 <= byte_length <= MAX_ASSET_BYTES
        ):
            raise ValueError(f"asset.byte_length must be between 0 and {MAX_ASSET_BYTES}")
        width = data.get("width")
        height = data.get("height")
        parsed_width: int | None = None
        parsed_height: int | None = None
        if width is not None or height is not None:
            if (
                isinstance(width, bool)
                or not isinstance(width, int)
                or width <= 0
                or isinstance(height, bool)
                or not isinstance(height, int)
                or height <= 0
            ):
                raise ValueError("asset.width and asset.height must be positive integers")
            parsed_width = width
            parsed_height = height
        if media_type == "image/rgb565":
            if parsed_width is None or parsed_height is None:
                raise ValueError("image/rgb565 assets require width and height")
            if byte_length != parsed_width * parsed_height * 2:
                raise ValueError("image/rgb565 byte_length must equal width*height*2")
        return cls(
            asset_id=_string(data.get("asset_id"), "asset.asset_id"),
            sha256=sha256,
            media_type=media_type,
            byte_length=byte_length,
            width=parsed_width,
            height=parsed_height,
        )

    def to_dict(self) -> JsonObject:
        document: JsonObject = {
            "asset_id": self.asset_id,
            "sha256": self.sha256,
            "media_type": self.media_type,
            "byte_length": self.byte_length,
        }
        if self.width is not None:
            document["width"] = self.width
        if self.height is not None:
            document["height"] = self.height
        return document
