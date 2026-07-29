"""Display backends for the Raspberry Pi renderer."""

from __future__ import annotations

import mmap
import os
from pathlib import Path
from typing import Protocol, runtime_checkable


class DisplayError(RuntimeError):
    """Raised when a display backend cannot be opened or written."""


@runtime_checkable
class DisplayBackend(Protocol):
    """Frame sink used by the renderer without exposing hardware details."""

    width: int
    height: int
    frame_size: int

    def open(self) -> None: ...

    def write_frame(self, frame: bytes | bytearray | memoryview) -> None: ...

    def write_rows(
        self,
        frame: bytes | bytearray | memoryview,
        start_row: int,
        end_row: int,
    ) -> None: ...

    def close(self) -> None: ...


class FramebufferBackend:
    """Memory-mapped RGB565 Linux framebuffer.

    Geometry is supplied from the verified ``fbset`` output. This backend does
    not configure the kernel driver, rotate frames, or access SPI directly.
    """

    bytes_per_pixel = 2

    def __init__(self, device: Path, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("framebuffer dimensions must be positive")
        self.device = device
        self.width = width
        self.height = height
        self.frame_size = width * height * self.bytes_per_pixel
        self._fd: int | None = None
        self._mapping: mmap.mmap | None = None

    @property
    def is_open(self) -> bool:
        return self._mapping is not None

    def open(self) -> None:
        if self.is_open:
            return
        try:
            fd = os.open(self.device, os.O_RDWR)
            # Unix defaults are MAP_SHARED and PROT_READ | PROT_WRITE.
            mapping = mmap.mmap(fd, self.frame_size)
        except OSError as exc:
            if "fd" in locals():
                os.close(fd)
            raise DisplayError(f"cannot open framebuffer {self.device}: {exc}") from exc
        self._fd = fd
        self._mapping = mapping

    def write_frame(self, frame: bytes | bytearray | memoryview) -> None:
        mapping = self._mapping
        if mapping is None:
            raise DisplayError("framebuffer is not open")
        view = self._validated_frame(frame)
        mapping.seek(0)
        mapping.write(view)

    def write_rows(
        self,
        frame: bytes | bytearray | memoryview,
        start_row: int,
        end_row: int,
    ) -> None:
        mapping = self._mapping
        if mapping is None:
            raise DisplayError("framebuffer is not open")
        view = self._validated_frame(frame)
        start, end = self._row_range(start_row, end_row)
        mapping.seek(start)
        mapping.write(view[start:end])

    def _validated_frame(self, frame: bytes | bytearray | memoryview) -> memoryview:
        view = memoryview(frame)
        if view.nbytes != self.frame_size:
            raise DisplayError(
                f"frame has {view.nbytes} bytes; expected {self.frame_size} "
                f"for {self.width}x{self.height} RGB565"
            )
        return view.cast("B") if view.format != "B" else view

    def _row_range(self, start_row: int, end_row: int) -> tuple[int, int]:
        if not 0 <= start_row < end_row <= self.height:
            raise DisplayError(f"row range must satisfy 0 <= start < end <= {self.height}")
        stride = self.width * self.bytes_per_pixel
        return start_row * stride, end_row * stride

    def close(self) -> None:
        mapping, fd = self._mapping, self._fd
        self._mapping = None
        self._fd = None
        if mapping is not None:
            mapping.close()
        if fd is not None:
            os.close(fd)


class HeadlessBackend:
    """In-memory backend for tests and development without Pi hardware."""

    bytes_per_pixel = 2

    def __init__(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("display dimensions must be positive")
        self.width = width
        self.height = height
        self.frame_size = width * height * self.bytes_per_pixel
        self.last_frame: bytes | None = None
        self._buffer = bytearray(self.frame_size)
        self.is_open = False

    def open(self) -> None:
        self.is_open = True

    def write_frame(self, frame: bytes | bytearray | memoryview) -> None:
        if not self.is_open:
            raise DisplayError("headless display is not open")
        view = memoryview(frame)
        if view.nbytes != self.frame_size:
            raise DisplayError(
                f"frame has {view.nbytes} bytes; expected {self.frame_size} "
                f"for {self.width}x{self.height} RGB565"
            )
        self._buffer[:] = view.cast("B") if view.format != "B" else view
        self.last_frame = bytes(self._buffer)

    def write_rows(
        self,
        frame: bytes | bytearray | memoryview,
        start_row: int,
        end_row: int,
    ) -> None:
        if not self.is_open:
            raise DisplayError("headless display is not open")
        view = memoryview(frame)
        if view.nbytes != self.frame_size:
            raise DisplayError(
                f"frame has {view.nbytes} bytes; expected {self.frame_size} "
                f"for {self.width}x{self.height} RGB565"
            )
        if not 0 <= start_row < end_row <= self.height:
            raise DisplayError(f"row range must satisfy 0 <= start < end <= {self.height}")
        stride = self.width * self.bytes_per_pixel
        start, end = start_row * stride, end_row * stride
        byte_view = view.cast("B") if view.format != "B" else view
        self._buffer[start:end] = byte_view[start:end]
        self.last_frame = bytes(self._buffer)

    def close(self) -> None:
        self.is_open = False
