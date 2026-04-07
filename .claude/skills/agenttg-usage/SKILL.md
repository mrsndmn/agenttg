---
name: agenttg-usage
description: "agenttg Library Usage\nTRIGGER when: code imports `agenttg`, or user asks about sending Telegram messages, formatting markdown for Telegram, rendering tables as PNG for Telegram, or using the agenttg library.\nDO NOT TRIGGER when: code imports other messaging libraries (slack_sdk, discord.py, etc.), general Telegram Bot API questions unrelated to agenttg."
---

# agenttg Library Usage

agenttg converts Markdown to Telegram-compatible formatting and provides
a thin HTTP client for the Telegram Bot API.

## Arkhip integration note

In Arkhip (`research_loop`), prefer importing Telegram helpers from
`research_loop.telegram.api`, `research_loop.telegram.parsing`, and
`research_loop.telegram.constants`. The legacy `telegram_notify.py` module is
kept as a backward-compatibility shim and should not be used in new code.

This skill pairs well with the official **agent-sdk-dev** plugin when building
Telegram-based agents with the Claude Agent SDK — use agenttg for message
formatting and delivery, and agent-sdk-dev for the agent orchestration layer.

## Installation

```bash
pip install agenttg
# or as git dependency:
pip install git+https://github.com/mrsndmn/agenttg.git@main
```

System requirements for table-to-PNG rendering (optional):
- `pandoc` - markdown to HTML conversion
- `wkhtmltoimage` (from wkhtmltopdf) - HTML to PNG rendering

## Core formatting

```python
import agenttg

# Escape text for MarkdownV2 (preserves **bold**, `code`, [links](url))
safe = agenttg.escape_markdownv2("Price: $10.00 (50% off)")

# Convert full markdown to Telegram MarkdownV2
# - Tables wrapped in code blocks
# - Headers become emoji + bold
formatted = agenttg.format_markdown(body)

# Split long text at newline boundaries (default limit: 4096)
parts = agenttg.split_text(formatted, limit=4096)

# Escape for HTML parse_mode
html_safe = agenttg.escape_html("<script>alert('xss')</script>")

# Segment body into text/table/image parts
segments = agenttg.split_body_into_segments(body)
for seg in segments:
    if seg.kind == "text": ...
    elif seg.kind == "table": ...
    elif seg.kind == "image": ...
```

## Sending messages

```python
import agenttg

TOKEN = "123:ABC"
CHAT_ID = "456"

# Plain text
agenttg.send_reply(TOKEN, CHAT_ID, "Hello!")

# MarkdownV2 with auto-segmentation (text/table/image)
# Tables are rendered as PNG images if pandoc+wkhtmltoimage available
agenttg.send_reply_markdown(TOKEN, CHAT_ID, markdown_body)

# HTML
agenttg.send_reply_html(TOKEN, CHAT_ID, "<b>Bold</b>")

# Photo
from pathlib import Path
agenttg.send_photo(TOKEN, CHAT_ID, Path("chart.png"), caption="Results")

# MarkdownV2 text parts with [1/N] prefix for multi-part messages
agenttg.send_text_parts(TOKEN, CHAT_ID, parts, add_part_prefix=True)

# Reactions
agenttg.set_message_reaction(TOKEN, CHAT_ID, message_id=42, emoji="\U0001f440")

# Bot info
username = agenttg.fetch_bot_username(TOKEN)

# Poll for updates
offset, messages = agenttg.get_updates(TOKEN, CHAT_ID, offset=0)
offset, all_messages = agenttg.get_all_updates(TOKEN, offset=0)
```

## Formatting error fallback

All sending functions that use a `parse_mode` (`send_text_parts`, `send_reply_html`,
`send_reply_markdown`) automatically detect Telegram's "can't parse entities" error
(HTTP 400) and retry the message without formatting, delivering it as plain text.
This ensures messages are always delivered even if the markup is malformed.

Additionally, `send_reply_markdown` falls back to sending tables as formatted code
blocks when the table-to-PNG rendering fails (e.g. `pandoc`/`wkhtmltopdf` not installed).

## Table to PNG

```python
from agenttg import md_table_to_png

png_path = md_table_to_png(
    "| A | B |\n|---|---|\n| 1 | 2 |",
    highlight_max=True,  # highlight max values in numerical columns
    width=2100,
)
```

## Data types

- `agenttg.ImageReference(path, caption)` - local image file reference
- `agenttg.BodySegment(kind, content, image)` - text/table/image segment
- `agenttg.TELEGRAM_TEXT_LIMIT` - 4096

## Testing

```bash
# Unit tests (no credentials needed)
pytest -m "not e2e"

# E2E tests (need Telegram credentials)
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... pytest -m e2e
```
