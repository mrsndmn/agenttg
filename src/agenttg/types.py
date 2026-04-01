"""Data types for Telegram message segmentation."""

from __future__ import annotations

import dataclasses
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class ImageReference:
    """Reference to a local image file with optional caption."""

    path: Path
    caption: str = ""


@dataclasses.dataclass(frozen=True)
class BodySegment:
    """A segment of message body: text, table, or image."""

    kind: str  # "text" | "table" | "image"
    content: str = ""
    image: ImageReference | None = None
