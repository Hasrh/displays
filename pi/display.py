"""Display hardware abstraction boundary."""

from typing import Protocol


class DisplayBackend(Protocol):
    """Minimal lifecycle contract; concrete framebuffer/KMS backends are deferred."""

    def open(self) -> None: ...

    def close(self) -> None: ...
