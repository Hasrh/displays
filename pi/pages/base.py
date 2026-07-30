"""Page rendering contract."""

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from pi.assets import AssetCache
from pi.canvas import RGB565Canvas
from pi.state import StoreSnapshot
from pi.themes import Theme


@dataclass(frozen=True, slots=True)
class RenderContext:
    snapshot: StoreSnapshot
    fft_bins: tuple[float, ...]
    measured_fps: float
    assets: AssetCache | None = None
    progress_pulse: float = 1.0
    transition_progress: float = 1.0
    now_seconds: float = 0.0

    def album_art(self, asset_id: str | None) -> NDArray[np.uint16] | None:
        if self.assets is None:
            return None
        return self.assets.get_rgb565(asset_id)


class Page(Protocol):
    @property
    def page_id(self) -> str: ...

    @property
    def revision(self) -> int: ...

    @property
    def continuous_updates(self) -> bool: ...

    @property
    def partial_update_row(self) -> int: ...

    def render(self, canvas: RGB565Canvas, context: RenderContext, theme: Theme) -> None: ...
