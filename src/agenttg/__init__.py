"""agenttg — Markdown-to-Telegram formatting and API client for agents."""

from .api import (
    fetch_bot_username,
    get_all_updates,
    get_updates,
    make_session,
    send_document,
    send_photo,
    send_reply,
    send_reply_html,
    send_reply_markdown,
    send_text_parts,
    send_video,
    set_message_reaction,
)
from .constants import TELEGRAM_TEXT_LIMIT
from .formatting import (
    escape_html,
    escape_markdownv2,
    format_markdown,
    parse_document_reference_line,
    parse_image_reference_line,
    parse_media_reference_line,
    parse_video_reference_line,
    split_body_into_segments,
    split_text,
)
from .rich_message import (
    RICH_BLOCK_LIMIT,
    RICH_TABLE_COLUMN_LIMIT,
    RICH_TEXT_LIMIT,
    rich_table_within_limits,
    send_rich_markdown,
    table_dimensions,
)
from .table_modes import (
    DEFAULT_TABLE_MODE,
    TABLE_MODE_ENV,
    TABLE_MODES,
    resolve_table_mode,
    table_render_chain,
)
from .table_to_png import md_table_to_png
from .types import BodySegment, ImageReference

__all__ = [
    "BodySegment",
    "DEFAULT_TABLE_MODE",
    "ImageReference",
    "RICH_BLOCK_LIMIT",
    "RICH_TABLE_COLUMN_LIMIT",
    "RICH_TEXT_LIMIT",
    "TABLE_MODES",
    "TABLE_MODE_ENV",
    "TELEGRAM_TEXT_LIMIT",
    "escape_html",
    "escape_markdownv2",
    "fetch_bot_username",
    "format_markdown",
    "get_all_updates",
    "get_updates",
    "make_session",
    "md_table_to_png",
    "parse_document_reference_line",
    "parse_image_reference_line",
    "parse_media_reference_line",
    "parse_video_reference_line",
    "resolve_table_mode",
    "rich_table_within_limits",
    "send_document",
    "send_photo",
    "send_reply",
    "send_reply_html",
    "send_reply_markdown",
    "send_rich_markdown",
    "send_text_parts",
    "send_video",
    "set_message_reaction",
    "split_body_into_segments",
    "split_text",
    "table_dimensions",
    "table_render_chain",
]
