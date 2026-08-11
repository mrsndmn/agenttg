"""Telegram rich messages (``sendRichMessage``, Bot API 10.2).

A rich message carries structured content — headings, lists, block quotations and,
the reason this module exists, **real tables** rendered by the Telegram client
instead of a screenshot or a fixed-width block.

Content is supplied through ``InputRichMessage``, which takes exactly one of
``html``, ``markdown`` or ``blocks``. We use ``markdown``: Telegram's Rich Markdown
is GitHub-Flavored-Markdown compatible, so an agent's markdown table goes over the
wire verbatim — no block tree to build, no cell model to maintain.

See https://core.telegram.org/bots/api#rich-message-formatting-options
"""

from __future__ import annotations

import logging
import re

import requests

from .transport import _request_with_retry, make_session

logger = logging.getLogger("agenttg")

#: Documented rich-message limits (see "Rich Message Limits" in the Bot API docs).
RICH_TEXT_LIMIT = 32768
RICH_BLOCK_LIMIT = 500
RICH_TABLE_COLUMN_LIMIT = 20

#: Split a table row on unescaped pipes only, so ``\|`` inside a cell stays a cell.
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")

#: A GFM delimiter row, e.g. ``|:---|---:|`` — it carries alignment, not content.
_DELIMITER_ROW_RE = re.compile(r"^\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?$")


def _split_row(line: str) -> list[str]:
    """Split one markdown table row into its cells."""
    cells = _UNESCAPED_PIPE_RE.split(line.strip())
    # A well-formed row is delimited on both ends, producing empty edge fields.
    if cells and not cells[0].strip():
        cells = cells[1:]
    if cells and not cells[-1].strip():
        cells = cells[:-1]
    return cells


def table_dimensions(md_table: str) -> tuple[int, int]:
    """Return ``(rows, columns)`` of a markdown table, ignoring the delimiter row."""
    rows = 0
    columns = 0
    for line in md_table.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _DELIMITER_ROW_RE.match(stripped):
            continue
        rows += 1
        columns = max(columns, len(_split_row(stripped)))
    return (rows, columns)


def rich_table_within_limits(md_table: str) -> tuple[bool, str]:
    """Check a markdown table against the documented rich-message limits.

    Returns ``(True, "")`` when the table can be sent as a rich message, or
    ``(False, reason)`` when it cannot — checked before the API call so an
    oversized table falls through the render chain instead of costing a round
    trip and a 400.
    """
    if len(md_table) > RICH_TEXT_LIMIT:
        return (False, f"text is {len(md_table)} chars (limit {RICH_TEXT_LIMIT})")
    rows, columns = table_dimensions(md_table)
    if columns > RICH_TABLE_COLUMN_LIMIT:
        return (False, f"table has {columns} columns (limit {RICH_TABLE_COLUMN_LIMIT})")
    # Every row is a block, and the table itself is one more.
    if rows + 1 > RICH_BLOCK_LIMIT:
        return (False, f"table has {rows} rows (block limit {RICH_BLOCK_LIMIT})")
    return (True, "")


def send_rich_markdown(
    token: str,
    chat_id: str,
    markdown: str,
    reply_to_message_id: int | None = None,
    thread_id: int | None = None,
    session: requests.Session | None = None,
) -> requests.Response | None:
    """Send *markdown* as a Telegram rich message. Returns the response or None.

    ``sendRichMessage`` has no ``reply_to_message_id`` parameter, so a reply is
    expressed through ``reply_parameters``; it is sent with
    ``allow_sending_without_reply`` so a deleted parent never drops the table.
    """
    s = session or make_session()
    url = f"https://api.telegram.org/bot{token}/sendRichMessage"
    payload: dict[str, object] = {
        "chat_id": chat_id,
        "rich_message": {"markdown": markdown},
    }
    if reply_to_message_id is not None:
        payload["reply_parameters"] = {
            "message_id": reply_to_message_id,
            "allow_sending_without_reply": True,
        }
    if thread_id is not None:
        payload["message_thread_id"] = thread_id
    try:
        resp = _request_with_retry(s, "post", url, json=payload, timeout=30)
    except requests.RequestException as exc:
        logger.warning("Failed to send Telegram rich message: %s", exc)
        return None
    if resp.status_code != 200:
        logger.warning(
            "Telegram sendRichMessage returned %s: %s",
            resp.status_code,
            resp.text[:200],
        )
    return resp
