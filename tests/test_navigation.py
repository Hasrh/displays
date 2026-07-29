"""Page manager navigation tests."""

from dataclasses import dataclass

from pi.canvas import RGB565Canvas
from pi.navigation import PageManager
from pi.pages.base import RenderContext
from pi.state import LatestStateStore
from pi.themes import DARK_THEME, Theme


@dataclass
class StubPage:
    page_id: str
    revision: int = 0
    continuous_updates: bool = False
    partial_update_row: int = 10
    renders: int = 0

    def render(
        self,
        canvas: RGB565Canvas,
        context: RenderContext,
        theme: Theme,
    ) -> None:
        self.renders += 1


def context() -> RenderContext:
    return RenderContext(
        snapshot=LatestStateStore().snapshot(),
        fft_bins=(0.0,) * 64,
        measured_fps=9.0,
    )


def test_manual_navigation_wraps_and_tracks_revision() -> None:
    pages = (StubPage("one"), StubPage("two"), StubPage("three"))
    manager = PageManager(pages, initial_page="two", auto_cycle_seconds=0)
    assert manager.current_page_id == "two"
    manager.next()
    assert manager.current_page_id == "three"
    manager.next()
    assert manager.current_page_id == "one"
    manager.previous()
    assert manager.current_page_id == "three"
    assert manager.revision == 3


def test_automatic_navigation_advances_during_render() -> None:
    now = [100.0]
    pages = (StubPage("one"), StubPage("two"))
    manager = PageManager(
        pages,
        initial_page="one",
        auto_cycle_seconds=5,
        clock=lambda: now[0],
    )
    canvas = RGB565Canvas(32, 24)
    manager.render(canvas, context(), DARK_THEME)
    assert manager.current_page_id == "one"
    now[0] = 105.0
    manager.render(canvas, context(), DARK_THEME)
    assert manager.current_page_id == "two"
    assert manager.revision == 1
