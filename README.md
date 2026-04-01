# agenttg

Markdown-to-Telegram formatting and API client for agents.

## Installation

```bash
pip install git+https://github.com/mrsndmn/agenttg.git@main
```

Optional system dependencies for table-to-PNG rendering:
```bash
apt-get install pandoc wkhtmltopdf
```

## Quick start

```python
import agenttg

TOKEN = "your-bot-token"
CHAT_ID = "your-chat-id"

# Send plain text
agenttg.send_reply(TOKEN, CHAT_ID, "Hello!")

# Send markdown with auto-formatting for Telegram MarkdownV2
# Tables become PNG images, headers get emoji prefixes, special chars are escaped
agenttg.send_reply_markdown(TOKEN, CHAT_ID, """
## Results

| Model | Accuracy | F1 |
|-------|---------|-----|
| A     | 95.2    | 0.94|
| B     | 92.1    | 0.91|

**Model A** outperforms on all metrics.
""")

# Send HTML
agenttg.send_reply_html(TOKEN, CHAT_ID, "<b>Bold</b> and <i>italic</i>")
```

## Formatting utilities

```python
# Escape for MarkdownV2 (preserves **bold**, `code`, [links](url))
safe = agenttg.escape_markdownv2("Price: $10.00 (50% off)")

# Convert markdown to Telegram MarkdownV2 format
formatted = agenttg.format_markdown(markdown_text)

# Split long text respecting Telegram's 4096 char limit
parts = agenttg.split_text(text)

# Escape for HTML parse_mode
html_safe = agenttg.escape_html("<script>")

# Render markdown table to PNG image
from agenttg import md_table_to_png
png_path = md_table_to_png("| A | B |\n|---|---|\n| 1 | 2 |")
```

## Formatting error fallback

All sending functions that use a `parse_mode` (`send_text_parts`, `send_reply_html`, `send_reply_markdown`) automatically detect Telegram's "can't parse entities" error (HTTP 400) and retry the message without formatting, delivering it as plain text. This ensures messages are always delivered even if the markup is malformed.

Additionally, `send_reply_markdown` falls back to sending tables as formatted code blocks when the table-to-PNG rendering fails (e.g. `pandoc`/`wkhtmltopdf` not installed).

## API reference

### Sending
- `send_reply(token, chat_id, text)` - plain text
- `send_reply_markdown(token, chat_id, body)` - markdown with table/image segmentation
- `send_reply_html(token, chat_id, html)` - HTML formatted
- `send_photo(token, chat_id, path)` - photo upload
- `send_text_parts(token, chat_id, parts, add_part_prefix)` - multi-part MarkdownV2

### Polling
- `get_updates(token, chat_id, offset)` - poll single chat
- `get_all_updates(token, offset)` - poll all chats

### Utilities
- `set_message_reaction(token, chat_id, message_id, emoji)` - set emoji reaction
- `fetch_bot_username(token)` - get bot username via getMe

### Types
- `ImageReference(path, caption)` - local image reference
- `BodySegment(kind, content, image)` - message segment (text/table/image)
- `TELEGRAM_TEXT_LIMIT` - 4096

## Development

```bash
pip install -e ".[dev]"
pytest -m "not e2e"                    # unit tests
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... pytest -m e2e  # e2e tests
ruff check src/ tests/                 # lint
ruff format src/ tests/                # format
```

## License

MIT
