"""The title block at the top of the transcript."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.widgets import Static

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.events import Resize

ART = """\
███████╗███████╗███╗   ██╗███████╗ █████╗ ██╗
██╔════╝██╔════╝████╗  ██║██╔════╝██╔══██╗██║
███████╗█████╗  ██╔██╗ ██║███████╗███████║██║
╚════██║██╔══╝  ██║╚██╗██║╚════██║██╔══██║██║
███████║███████╗██║ ╚████║███████║██║  ██║██║
╚══════╝╚══════╝╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝╚═╝"""
ART_WIDTH = max(len(line) for line in ART.splitlines())
TITLE = "Sensai"


class Banner(Vertical):
    """A big "Sensai" and a subtitle, naming the session shown below.

    The block letters need `ART_WIDTH` columns; a narrower terminal gets the
    plain title.
    """

    DEFAULT_CSS = """
    Banner {
        height: auto;
        margin: 1 0 0 0;

        .banner-art {
            height: auto;
            color: $primary;
            text-style: bold;
        }
        .banner-title {
            height: 1;
            color: $primary;
            text-style: bold;
        }
        .banner-subtitle {
            height: 1;
            color: $text-muted;
        }
    }
    """

    def __init__(self, subtitle: str) -> None:
        """Show `subtitle` under the title."""
        super().__init__()
        self.subtitle = subtitle

    def compose(self) -> ComposeResult:
        """Lay out the block letters, the plain title and the subtitle."""
        yield Static(ART, classes="banner-art", markup=False)
        yield Static(TITLE, classes="banner-title", markup=False)
        yield Static(self.subtitle, classes="banner-subtitle", markup=False)

    def on_mount(self) -> None:
        """Pick the title that fits."""
        self._fit(self.size.width or self.app.size.width)

    def on_resize(self, event: Resize) -> None:
        """Pick the title that fits the new width."""
        self._fit(event.size.width)

    def _fit(self, width: int) -> None:
        big = width >= ART_WIDTH
        self.query_one(".banner-art").display = big
        self.query_one(".banner-title").display = not big
