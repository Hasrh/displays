"""Page rendering contract."""

from dataclasses import dataclass
from typing import Protocol

from pi.canvas import RGB565Canvas
from pi.state import StoreSnapshot
from pi.themes import Theme


@dataclass(frozen=True, slots=True)
class RenderContext:
    snapshot: StoreSnapshot
    fft_bins: tuple[float, ...]
    measured_fps: float


class Page(Protocol):
    partial_update_row: int

    def render(self, canvas: RGB565Canvas, context: RenderContext, theme: Theme) -> None: ...
