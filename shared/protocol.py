"""Protocol boundary vocabulary without transport or codec implementation."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from shared.constants import MessageType


@dataclass(frozen=True, slots=True)
class Envelope:
    """In-memory shape of the agreed JSON envelope.

    Validation, JSON codecs, version negotiation, and binary asset framing are intentionally
    deferred to the protocol-contract milestone.
    """

    protocol_version: str
    type: MessageType
    message_id: str
    sent_at: str
    sequence: int
    payload: Mapping[str, Any]
