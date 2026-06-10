"""MarkdownV2 escaping, formatting, and body segmentation for Telegram messages."""

from __future__ import annotations

import re
from pathlib import Path

from .constants import (
    _BARE_FILE_RE,
    _BARE_IMAGE_RE,
    _BARE_VIDEO_RE,
    _HTTP_PREFIXES,
    _IMAGE_EXTENSIONS,
    _MARKDOWNV2_ESCAPE_CHARS,
    _MD_IMAGE_RE,
    _MD_LINK_RE,
    _MEDIA_EXTENSIONS,
    _PLACEHOLDER_BASE,
    _VIDEO_EXTENSIONS,
    TELEGRAM_TEXT_LIMIT,
)
from .types import BodySegment, ImageReference


def escape_markdownv2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2, preserving markdown entities.

    Preserves: **bold**, __underline__, `code`, [links](url), etc.
    Escapes other special chars: _*[]()~`>#+-=|{}.!
    Uses Unicode private-use chars as placeholders so they are not escaped.
    """
    placeholders: dict[str, str] = {}
    placeholder_idx = 0

    def make_placeholder() -> str:
        nonlocal placeholder_idx
        ph = chr(_PLACEHOLDER_BASE + placeholder_idx)
        placeholder_idx += 1
        return ph

    protected_text = text

    def protect_code(m: re.Match[str]) -> str:
        ph = make_placeholder()
        placeholders[ph] = m.group(0)
        return ph

    protected_text = re.sub(r"`[^`]+`", protect_code, protected_text)

    def protect_bold(m: re.Match[str]) -> str:
        ph = make_placeholder()
        # Convert standard Markdown **bold** to MarkdownV2 *bold*
        inner = m.group(0)[2:-2]
        placeholders[ph] = f"*{inner}*"
        return ph

    protected_text = re.sub(r"\*\*[^*]+\*\*", protect_bold, protected_text)

    def protect_underline(m: re.Match[str]) -> str:
        ph = make_placeholder()
        placeholders[ph] = m.group(0)
        return ph

    protected_text = re.sub(r"__[^_]+__", protect_underline, protected_text)

    def protect_link(m: re.Match[str]) -> str:
        ph = make_placeholder()
        # Pre-escape link parts: structural []() stay intact,
        # text and URL contents are escaped separately.
        text = m.group(1)
        url = m.group(2)
        _escape_in_link_text = set("_*[]()~`>#+-=|{}.!\\")
        _escape_in_url = set(")\\")
        escaped_text = "".join("\\" + c if c in _escape_in_link_text else c for c in text)
        escaped_url = "".join("\\" + c if c in _escape_in_url else c for c in url)
        placeholders[ph] = f"[{escaped_text}]({escaped_url})"
        return ph

    protected_text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", protect_link, protected_text)

    result = []
    for char in protected_text:
        if char == "\\":
            result.append("\\\\")
        elif char in _MARKDOWNV2_ESCAPE_CHARS:
            result.append("\\" + char)
        else:
            result.append(char)
    escaped = "".join(result)

    _escape_inside_entity = set("()\\.[]~>#+-=|{}!")
    for placeholder_char, original in reversed(list(placeholders.items())):
        # Links are pre-escaped during protection; insert as-is.
        if original.startswith("[") and "](" in original and original.endswith(")"):
            escaped = escaped.replace(placeholder_char, original)
        else:
            escaped_original = "".join(
                "\\" + c if c in _escape_inside_entity else c for c in original
            )
            escaped = escaped.replace(placeholder_char, escaped_original)

    return escaped


def format_markdown(text: str) -> str:
    """Convert markdown to Telegram MarkdownV2 format.

    Rules:
    1. Tables (lines starting with |) are wrapped in code blocks
    2. Headers (# Header) are converted to ➡️ *Header* (bold with emoji prefix)
    3. Special characters are escaped for MarkdownV2 (preserving markdown entities)
    """
    lines = text.split("\n")
    result: list[str] = []
    in_table = False
    table_lines: list[str] = []

    i = 0
    in_code_block = False
    while i < len(lines):
        line = lines[i]

        # Handle code blocks (triple backticks) — pass through unescaped
        if line.strip().startswith("```"):
            if in_code_block:
                result.append("```")
                in_code_block = False
                i += 1
                continue
            else:
                in_code_block = True
                result.append(line.strip())
                i += 1
                continue

        if in_code_block:
            result.append(line)
            i += 1
            continue

        if line.strip().startswith("|"):
            if not in_table:
                in_table = True
                table_lines = []
            table_lines.append(line)
            i += 1
            continue

        if in_table:
            result.append("```")
            result.extend(table_lines)
            result.append("```")
            in_table = False
            table_lines = []

        header_match = re.match(r"^(#+)\s+(.+)$", line)
        if header_match:
            header_text = header_match.group(2).strip()
            escaped_header = escape_markdownv2(header_text)
            result.append(f"➡️ *{escaped_header}*")
            i += 1
            continue

        escaped_line = escape_markdownv2(line)
        result.append(escaped_line)
        i += 1

    if in_code_block:
        # Unclosed code block — close it
        result.append("```")

    if in_table:
        result.append("```")
        result.extend(table_lines)
        result.append("```")

    return "\n".join(result)


def split_text(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    """Split text into chunks at or under limit, preferring newline boundaries."""
    if len(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        chunk = rest[:limit]
        last_nl = chunk.rfind("\n")
        split_at = last_nl + 1 if last_nl > limit // 2 else limit
        chunks.append(rest[:split_at])
        rest = rest[split_at:].lstrip("\n")
    return chunks


def escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram parse_mode=HTML."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _to_local_media_reference(
    raw_path: str,
    caption: str = "",
    allowed_extensions: set[str] = _MEDIA_EXTENSIONS,
    workdir: Path | None = None,
) -> ImageReference | None:
    """Resolve a raw path to a local media file reference.

    Returns an ImageReference if the path points to a local file with a
    matching extension, or None otherwise.  *workdir* overrides ``Path.cwd()``
    for resolving relative paths.
    """
    candidate = raw_path.strip().strip('"').strip("'")
    if not candidate:
        return None
    if candidate.startswith(_HTTP_PREFIXES):
        return None
    path = Path(candidate)
    base = workdir if workdir is not None else Path.cwd()
    path = (base / path).resolve() if not path.is_absolute() else path.resolve()
    if path.suffix.lower() not in allowed_extensions:
        return None
    if not path.is_file():
        return None
    return ImageReference(path=path, caption=caption.strip())


def _to_local_image_reference(
    raw_path: str, caption: str = "", workdir: Path | None = None
) -> ImageReference | None:
    return _to_local_media_reference(raw_path, caption, _IMAGE_EXTENSIONS, workdir=workdir)


def parse_image_reference_line(line: str, workdir: Path | None = None) -> ImageReference | None:
    """Parse a single line for image references.

    Supports: ![caption](path), [caption](path), bare paths ending in image extensions.
    """
    md_image = _MD_IMAGE_RE.match(line)
    if md_image:
        return _to_local_image_reference(
            md_image.group("path"), md_image.group("caption"), workdir=workdir
        )

    md_link = _MD_LINK_RE.match(line)
    if md_link:
        return _to_local_image_reference(
            md_link.group("path"), md_link.group("caption"), workdir=workdir
        )

    bare = _BARE_IMAGE_RE.match(line)
    if bare:
        return _to_local_image_reference(bare.group("path"), workdir=workdir)

    return None


def parse_video_reference_line(line: str, workdir: Path | None = None) -> ImageReference | None:
    """Parse a single line for video references.

    Supports: ![caption](path), [caption](path), bare paths ending in video extensions.
    """
    md_image = _MD_IMAGE_RE.match(line)
    if md_image:
        return _to_local_media_reference(
            md_image.group("path"), md_image.group("caption"), _VIDEO_EXTENSIONS, workdir=workdir
        )

    md_link = _MD_LINK_RE.match(line)
    if md_link:
        return _to_local_media_reference(
            md_link.group("path"), md_link.group("caption"), _VIDEO_EXTENSIONS, workdir=workdir
        )

    bare = _BARE_VIDEO_RE.match(line)
    if bare:
        return _to_local_media_reference(
            bare.group("path"), allowed_extensions=_VIDEO_EXTENSIONS, workdir=workdir
        )

    return None


def _to_local_file_reference(
    raw_path: str, caption: str = "", workdir: Path | None = None
) -> ImageReference | None:
    """Resolve a raw path to any local file (for document uploads)."""
    candidate = raw_path.strip().strip('"').strip("'")
    if not candidate:
        return None
    if candidate.startswith(_HTTP_PREFIXES):
        return None
    path = Path(candidate)
    base = workdir if workdir is not None else Path.cwd()
    path = (base / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.suffix:
        return None
    if not path.is_file():
        return None
    return ImageReference(path=path, caption=caption.strip())


def parse_document_reference_line(line: str, workdir: Path | None = None) -> ImageReference | None:
    """Parse a single line for document file references.

    Matches any local file path that is not an image or video.
    Supports: ![caption](path), [caption](path), bare paths with an extension.
    """
    for regex in (_MD_IMAGE_RE, _MD_LINK_RE):
        m = regex.match(line)
        if m:
            raw = m.group("path")
            # Skip if it's an image or video extension
            suffix = Path(raw.strip().strip('"').strip("'")).suffix.lower()
            if suffix in _MEDIA_EXTENSIONS:
                return None
            return _to_local_file_reference(raw, m.group("caption"), workdir=workdir)

    bare = _BARE_FILE_RE.match(line)
    if bare:
        raw = bare.group("path")
        suffix = Path(raw).suffix.lower()
        if suffix in _MEDIA_EXTENSIONS:
            return None
        return _to_local_file_reference(raw, workdir=workdir)

    return None


def parse_media_reference_line(
    line: str, workdir: Path | None = None
) -> tuple[str, ImageReference | None]:
    """Parse a line for any media reference (image, video, or document).

    Returns (kind, reference) where kind is "image", "video", "document", or "none".
    """
    ref = parse_video_reference_line(line, workdir=workdir)
    if ref is not None:
        return ("video", ref)
    ref = parse_image_reference_line(line, workdir=workdir)
    if ref is not None:
        return ("image", ref)
    ref = parse_document_reference_line(line, workdir=workdir)
    if ref is not None:
        return ("document", ref)
    return ("none", None)


def split_body_into_segments(body: str, workdir: Path | None = None) -> list[BodySegment]:
    """Split body into alternating text, table, image, video, and document segments."""
    lines = body.split("\n")
    segments: list[BodySegment] = []
    text_lines: list[str] = []

    def flush_text() -> None:
        if text_lines:
            segments.append(BodySegment(kind="text", content="\n".join(text_lines)))
            text_lines.clear()

    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            flush_text()
            table_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            segments.append(BodySegment(kind="table", content="\n".join(table_lines)))
        else:
            kind, media_ref = parse_media_reference_line(lines[i], workdir=workdir)
            if media_ref is not None:
                flush_text()
                segments.append(BodySegment(kind=kind, image=media_ref))
                i += 1
                continue
            text_lines.append(lines[i])
            i += 1
    flush_text()
    return segments
