"""Stable protocol vocabulary and conservative limits."""

from enum import StrEnum

PROTOCOL_VERSION = "1.0"
DEFAULT_LOG_LEVEL = "INFO"
MAX_JSON_MESSAGE_BYTES = 256 * 1024
MAX_ASSET_BYTES = 2 * 1024 * 1024
FFT_BIN_COUNT = 64
ASSET_FRAME_MAGIC = b"DDAS"
ASSET_FRAME_VERSION = 1


class MessageType(StrEnum):
    """Agreed JSON message families; codecs are a later delivery."""

    HELLO = "hello"
    WELCOME = "welcome"
    STATE_SNAPSHOT = "state_snapshot"
    STATE_PATCH = "state_patch"
    FFT_FRAME = "fft_frame"
    COMMAND = "command"
    COMMAND_RESULT = "command_result"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    ASSET_MANIFEST = "asset_manifest"


class CommandAction(StrEnum):
    """Commands accepted by either the host or the renderer."""

    PLAY_PAUSE = "play_pause"
    NEXT_TRACK = "next_track"
    PREVIOUS_TRACK = "previous_track"
    SET_VOLUME = "set_volume"
    SET_BRIGHTNESS = "set_brightness"
    NAVIGATE = "navigate"
