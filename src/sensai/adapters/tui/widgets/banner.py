"""The title block at the top of the transcript."""

from __future__ import annotations

import random
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
# One is picked at random each time the banner is shown, like a Minecraft splash.
MOTDS = (
    "Now with 100% more tokens!",
    "Runs on your machine, thinks on its own.",
    "Ask me anything. Except the meaning of life.",
    "Try /tools to see what I can do.",
    "Try /sessions to pick up where you left off.",
    "Press ctrl+t to peek at my thoughts.",
    "No cloud was harmed in the making of this answer.",
    "Local models, global ambitions.",
    "I remember things. Ask me to forget.",
    "Powered by matrix multiplication.",
    "Also try /effort!",
    "Hallucinations are a feature, sometimes.",
    "Have you tried turning it off and on again?",
    "Is this thing on?",
    "Sensai says: drink some water.",
    "It works on my GPU.",
)


class Banner(Vertical):
    """A big "Sensai", the session shown below and a random splash line.

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
            margin: 1 0 0 0;
            color: $text-muted;
        }
        .banner-motd {
            height: 1;
            color: $text-disabled;
            text-style: italic;
        }
    }
    """

    def __init__(self, subtitle: str, motd: str | None = None) -> None:
        """Show `subtitle` under the title, then a splash line.

        Args:
            subtitle: What the transcript below is, such as the session's title.
            motd: The splash line; one of `MOTDS`, at random, if None.
        """
        super().__init__()
        self.subtitle = subtitle
        self.motd = motd if motd is not None else random.choice(MOTDS)

    def compose(self) -> ComposeResult:
        """Lay out the block letters, the plain title and the subtitle."""
        yield Static(ART, classes="banner-art", markup=False)
        yield Static(TITLE, classes="banner-title", markup=False)
        yield Static(self.subtitle, classes="banner-subtitle", markup=False)
        yield Static(self.motd, classes="banner-motd", markup=False)

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
