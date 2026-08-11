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

#: User-facing synonyms. ``table`` is how a native Telegram table is asked for in
#: chat (``/jobs_list fmt=table``, ``<!-- fmt=table -->``) — "rich" names the API
#: object, "table" names what the user sees.
TABLE_MODE_ALIASES: dict[str, str] = {
    "table": "rich",
    "png": "image",
    "photo": "image",
    "raw": "code",
}


def normalize_table_mode(mode: str | None) -> str | None:
    """Return the canonical mode name for *mode*, or ``None`` if it is not one.

    Accepts the canonical names plus :data:`TABLE_MODE_ALIASES`, case- and
    space-insensitively. An empty/unset value returns ``None``, as does an
    unrecognized one — callers decide whether that is a typo worth warning about.
    """
    candidate = (mode or "").strip().lower()
    if not candidate:
        return None
    candidate = TABLE_MODE_ALIASES.get(candidate, candidate)
    return candidate if candidate in TABLE_MODE_CHAINS else None


def resolve_table_mode(mode: str | None = None) -> str:
    """Return the effective table rendering mode.

    Precedence: explicit *mode* argument > ``AGENTTG_TABLE_MODE`` env var >
    :data:`DEFAULT_TABLE_MODE`. An unrecognized value is logged and **ignored** —
    an explicit typo falls back to the configured default rather than to the
    hardcoded one — so a bad override never blocks delivery.
    """
    if mode is not None and mode.strip():
        normalized = normalize_table_mode(mode)
        if normalized is not None:
            return normalized
        logger.warning(
            "Unknown table rendering mode %r (expected one of %s), ignoring it",
            mode.strip(),
            ", ".join(TABLE_MODES),
        )
    from_env = normalize_table_mode(os.environ.get(TABLE_MODE_ENV, ""))
    if from_env is not None:
        return from_env
    if os.environ.get(TABLE_MODE_ENV, "").strip():
        logger.warning(
            "Unknown %s=%r (expected one of %s), using %r",
            TABLE_MODE_ENV,
            os.environ[TABLE_MODE_ENV].strip(),
            ", ".join(TABLE_MODES),
            DEFAULT_TABLE_MODE,
        )
    return DEFAULT_TABLE_MODE


def table_render_chain(mode: str | None = None) -> tuple[str, ...]:
    """Return the ordered renderers to try for the given (or configured) mode."""
    return TABLE_MODE_CHAINS[resolve_table_mode(mode)]
