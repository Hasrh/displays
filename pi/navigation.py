"""Page lifecycle and navigation independent of touch hardware."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from time import monotonic

from pi.canvas import RGB565Canvas
from pi.pages.base import Page, RenderContext
from pi.pages.components import draw_page_indicator
from pi.themes import Theme


class PageManager:
    """Owns current-page state and optional automatic navigation."""

    page_id = "page_manager"

    def __init__(
        self,
        pages: Sequence[Page],
        *,
        initial_page: str,
        auto_cycle_seconds: float,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not pages:
            raise ValueError("at least one page is required")
        if auto_cycle_seconds < 0:
            raise ValueError("auto_cycle_seconds cannot be negative")
        identifiers = [page.page_id for page in pages]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("page identifiers must be unique")
        if initial_page not in identifiers:
            raise ValueError(f"unknown initial page {initial_page!r}")
        self._pages = tuple(pages)
        self._index = identifiers.index(initial_page)
        self._auto_cycle_seconds = auto_cycle_seconds
        self._clock = clock
        self._last_switch = clock()
        self.revision = 0

    @property
    def current(self) -> Page:
        return self._pages[self._index]

    @property
    def partial_update_row(self) -> int:
        return self.current.partial_update_row

    @property
    def continuous_updates(self) -> bool:
        return self.current.continuous_updates

    @property
    def current_page_id(self) -> str:
        return self.current.page_id

    def select(self, page_id: str) -> None:
        for index, page in enumerate(self._pages):
            if page.page_id == page_id:
                if index != self._index:
                    self._index = index
                    self.revision += 1
                self._last_switch = self._clock()
                return
        raise ValueError(f"unknown page {page_id!r}")

    def next(self) -> None:
        self._index = (self._index + 1) % len(self._pages)
        self.revision += 1
        self._last_switch = self._clock()

    def previous(self) -> None:
        self._index = (self._index - 1) % len(self._pages)
        self.revision += 1
        self._last_switch = self._clock()

    def render(self, canvas: RGB565Canvas, context: RenderContext, theme: Theme) -> None:
        self._advance_if_due()
        self.current.render(canvas, context, theme)
        draw_page_indicator(
            canvas,
            page_count=len(self._pages),
            selected_index=self._index,
            theme=theme,
        )

    def _advance_if_due(self) -> None:
        if self._auto_cycle_seconds <= 0:
            return
        now = self._clock()
        elapsed = now - self._last_switch
        if elapsed < self._auto_cycle_seconds:
            return
        steps = max(1, int(elapsed // self._auto_cycle_seconds))
        self._index = (self._index + steps) % len(self._pages)
        self.revision += steps
        self._last_switch += steps * self._auto_cycle_seconds
