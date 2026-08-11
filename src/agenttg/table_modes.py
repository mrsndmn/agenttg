"""Table rendering modes and their fallback chains.

A markdown table can be delivered to Telegram three ways:

``image``
    Rendered to PNG via pandoc + wkhtmltoimage and sent with ``sendPhoto``.
``rich``
    Sent as a native Telegram rich message (``sendRichMessage``, Bot API 10.2),
    which renders real tables client-side.
``code``
    The raw markdown wrapped in a fixed-width code block — always available, so
    it terminates every chain.

The configured mode is a *preference*, not a hard selection: each mode expands to
an ordered chain and the first link that succeeds wins, so a table is never lost
because pandoc is missing or the rich API rejected the payload.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("agenttg")

TABLE_MODE_ENV = "AGENTTG_TABLE_MODE"
DEFAULT_TABLE_MODE = "image"

#: Preferred mode -> ordered renderers to try. ``code`` always terminates a chain
#: because it needs neither external binaries nor a preflight check.
TABLE_MODE_CHAINS: dict[str, tuple[str, ...]] = {
    "image": ("image", "rich", "code"),
    "rich": ("rich", "image", "code"),
    "code": ("code",),
}

TABLE_MODES = tuple(TABLE_MODE_CHAINS)


def resolve_table_mode(mode: str | None = None) -> str:
    """Return the effective table rendering mode.

    Precedence: explicit *mode* argument > ``AGENTTG_TABLE_MODE`` env var >
    :data:`DEFAULT_TABLE_MODE`. Unknown values are logged and fall back to the
    default so a typo never blocks delivery.
    """
    raw = mode if mode is not None else os.environ.get(TABLE_MODE_ENV, "")
    candidate = (raw or "").strip().lower()
    if not candidate:
        return DEFAULT_TABLE_MODE
    if candidate not in TABLE_MODE_CHAINS:
        logger.warning(
            "Unknown table rendering mode %r (expected one of %s), using %r",
            candidate,
            ", ".join(TABLE_MODES),
            DEFAULT_TABLE_MODE,
        )
        return DEFAULT_TABLE_MODE
    return candidate


def table_render_chain(mode: str | None = None) -> tuple[str, ...]:
    """Return the ordered renderers to try for the given (or configured) mode."""
    return TABLE_MODE_CHAINS[resolve_table_mode(mode)]
