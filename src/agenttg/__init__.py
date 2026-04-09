"""agenttg — Markdown-to-Telegram formatting and API client for agents."""

from .api import (
    fetch_bot_username,
    get_all_updates,
    get_updates,
    make_session,
    send_photo,
    send_reply,
    send_reply_html,
    send_reply_markdown,
    send_text_parts,
    set_message_reaction,
)
from .constants import TELEGRAM_TEXT_LIMIT
from .formatting import (
    escape_html,
    escape_markdownv2,
    format_markdown,
    parse_image_reference_line,
    split_body_into_segments,
    split_text,
)
from .table_to_png import md_table_to_png
from .types import BodySegment, ImageReference

__all__ = [
    "BodySegment",
    "ImageReference",
    "TELEGRAM_TEXT_LIMIT",
    "escape_html",
    "escape_markdownv2",
    "fetch_bot_username",
    "format_markdown",
    "get_all_updates",
    "get_updates",
    "make_session",
    "md_table_to_png",
    "parse_image_reference_line",
    "send_photo",
    "send_reply",
    "send_reply_html",
    "send_reply_markdown",
    "send_text_parts",
    "set_message_reaction",
    "split_body_into_segments",
    "split_text",
]
