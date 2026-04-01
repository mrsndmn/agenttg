"""Telegram constants, escape characters, and regex patterns."""

from __future__ import annotations

import re

# Telegram message length limit
TELEGRAM_TEXT_LIMIT = 4096

# Characters that must be escaped in Telegram MarkdownV2 (except inside code/pre blocks)
_MARKDOWNV2_ESCAPE_CHARS = set("_*[]()~`>#+-=|{}.!")

# Unicode private-use characters (U+E000-E0FF) for placeholders; not escaped by MarkdownV2
_PLACEHOLDER_BASE = 0xE000

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_HTTP_PREFIXES = ("http://", "https://")
_MD_IMAGE_RE = re.compile(r"^\s*(?:[-*]\s+)?!\[(?P<caption>[^\]]*)\]\((?P<path>[^)]+)\)\s*$")
_MD_LINK_RE = re.compile(r"^\s*(?:[-*]\s+)?\[(?P<caption>[^\]]+)\]\((?P<path>[^)]+)\)\s*$")
_BARE_IMAGE_RE = re.compile(
    r"^\s*(?:[-*]\s+)?`?(?P<path>(?:/|\.{1,2}/)?[^\s`]+?\.(?:png|jpg|jpeg|webp))`?\s*$",
    re.IGNORECASE,
)
