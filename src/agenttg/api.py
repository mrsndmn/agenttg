"""Telegram HTTP API calls: send messages, photos, reactions, and poll updates."""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import suppress
from pathlib import Path

import requests

from .constants import TELEGRAM_TEXT_LIMIT
from .formatting import (
    escape_markdownv2,
    format_markdown,
    split_body_into_segments,
    split_text,
)
from .table_to_png import md_table_to_png

logger = logging.getLogger("agenttg")

_MAX_RETRIES = 3
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

def make_session() -> requests.Session:
    """Create a new session configured with TELEGRAM_HTTPS_PROXY if set."""
    session = requests.Session()
    proxy = os.environ.get("TELEGRAM_HTTPS_PROXY")
    if proxy:
        session.proxies = {"https": proxy}
        logger.info("Using TELEGRAM_HTTPS_PROXY for new session")
    return session


def _request_with_retry(session, http_method, url, **kwargs):
    """Execute an HTTP request with exponential backoff retry on transient errors."""
    files = kwargs.get("files")
    for attempt in range(_MAX_RETRIES):
        try:
            resp = getattr(session, http_method)(url, **kwargs)
            if resp.status_code not in _RETRY_STATUSES or attempt == _MAX_RETRIES - 1:
                return resp
            logger.warning(
                "Telegram API %s returned %s, retry %d/%d",
                url.rsplit("/", 1)[-1],
                resp.status_code,
                attempt + 1,
                _MAX_RETRIES - 1,
            )
        except requests.RequestException:
            if attempt == _MAX_RETRIES - 1:
                raise
            logger.warning(
                "Telegram API %s request failed, retry %d/%d",
                url.rsplit("/", 1)[-1],
                attempt + 1,
                _MAX_RETRIES - 1,
            )
        if files:
            for f in files.values():
                if hasattr(f, "seek"):
                    f.seek(0)
        time.sleep(2**attempt)


def send_photo(
    token: str,
    chat_id: str,
    png_path: Path,
    caption: str | None = None,
    delete_after_send: bool = True,
    reply_to_message_id: int | None = None,
    thread_id: int | None = None,
    session: requests.Session | None = None,
) -> requests.Response | None:
    """Send an image file as a photo to the chat. Returns response or None on failure."""
    s = session or make_session()
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    data: dict[str, object] = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption[:1024]
    if reply_to_message_id is not None:
        data["reply_to_message_id"] = reply_to_message_id
    if thread_id is not None:
        data["message_thread_id"] = thread_id
    try:
        with open(png_path, "rb") as f:
            resp = _request_with_retry(
                s,
                "post",
                url,
                data=data,
                files={"photo": f},
                timeout=60,
            )
        if resp.status_code != 200:
            logger.warning(
                "Telegram sendPhoto returned %s: %s",
                resp.status_code,
                resp.text[:200],
            )
        return resp
    except (requests.RequestException, OSError) as exc:
        logger.warning("Failed to send Telegram photo: %s", exc)
        return None
    finally:
        if delete_after_send and png_path.exists():
            with suppress(OSError):
                png_path.unlink()


def send_text_parts(
    token: str,
    chat_id: str,
    parts: list[str],
    add_part_prefix: bool,
    reply_to_message_id: int | None = None,
    thread_id: int | None = None,
    session: requests.Session | None = None,
) -> list[requests.Response]:
    """Send text parts as Telegram messages with MarkdownV2. Optionally add [1/N] prefix."""
    s = session or make_session()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    result: list[requests.Response] = []
    for i, part in enumerate(parts):
        if add_part_prefix and len(parts) > 1:
            prefix = escape_markdownv2(f"[{i + 1}/{len(parts)}]") + "\n"
            part = prefix + part
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": part,
            "parse_mode": "MarkdownV2",
        }
        if reply_to_message_id is not None and i == 0:
            payload["reply_to_message_id"] = reply_to_message_id
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        try:
            resp = _request_with_retry(s, "post", url, json=payload, timeout=10)
            result.append(resp)
            if resp.status_code == 400 and "can't parse entities" in resp.text.lower():
                logger.warning(
                    "Telegram MarkdownV2 parse error, retrying without formatting: %s",
                    resp.text[:200],
                )
                payload_plain = payload.copy()
                del payload_plain["parse_mode"]
                try:
                    resp_retry = _request_with_retry(
                        s, "post", url, json=payload_plain, timeout=10
                    )
                    result.append(resp_retry)
                    if resp_retry.status_code != 200:
                        logger.warning(
                            "Telegram plain text retry also failed %s: %s",
                            resp_retry.status_code,
                            resp_retry.text[:200],
                        )
                except requests.RequestException as exc_retry:
                    logger.warning("Failed to send Telegram plain text retry: %s", exc_retry)
            elif resp.status_code != 200:
                logger.warning(
                    "Telegram API returned %s: %s",
                    resp.status_code,
                    resp.text[:200],
                )
        except requests.RequestException as exc:
            logger.warning("Failed to send Telegram notification: %s", exc)
    return result


def send_reply(
    token: str,
    chat_id: str,
    text: str,
    reply_to_message_id: int | None = None,
    thread_id: int | None = None,
    session: requests.Session | None = None,
) -> list[requests.Response]:
    """Send a plain-text reply to the chat, optionally replying to a message."""
    s = session or make_session()
    parts = split_text(text, limit=TELEGRAM_TEXT_LIMIT)
    if not parts:
        return []
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    result: list[requests.Response] = []
    for i, part in enumerate(parts):
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": part,
        }
        if reply_to_message_id is not None and i == 0:
            payload["reply_to_message_id"] = reply_to_message_id
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        try:
            resp = _request_with_retry(s, "post", url, json=payload, timeout=10)
            result.append(resp)
            if resp.status_code != 200:
                logger.warning(
                    "Telegram API returned %s: %s",
                    resp.status_code,
                    resp.text[:200],
                )
        except requests.RequestException as exc:
            logger.warning("Failed to send Telegram reply: %s", exc)
    return result


def send_reply_html(
    token: str,
    chat_id: str,
    html: str,
    reply_to_message_id: int | None = None,
    thread_id: int | None = None,
    session: requests.Session | None = None,
) -> list[requests.Response]:
    """Send a reply with parse_mode=HTML."""
    s = session or make_session()
    if not html.strip():
        return []
    limit = TELEGRAM_TEXT_LIMIT
    if len(html) <= limit:
        parts = [html]
    else:
        parts = []
        rest = html
        while rest:
            if len(rest) <= limit:
                parts.append(rest)
                break
            chunk = rest[:limit]
            last_nl = chunk.rfind("\n")
            split_at = last_nl + 1 if last_nl > limit // 2 else limit
            parts.append(rest[:split_at])
            rest = rest[split_at:].lstrip("\n")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    result: list[requests.Response] = []
    for i, part in enumerate(parts):
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": part,
            "parse_mode": "HTML",
        }
        if reply_to_message_id is not None and i == 0:
            payload["reply_to_message_id"] = reply_to_message_id
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        try:
            resp = _request_with_retry(s, "post", url, json=payload, timeout=10)
            result.append(resp)
            if resp.status_code == 400 and "can't parse entities" in resp.text.lower():
                logger.warning(
                    "Telegram HTML parse error, retrying without formatting: %s",
                    resp.text[:200],
                )
                payload_plain = payload.copy()
                del payload_plain["parse_mode"]
                try:
                    resp_retry = _request_with_retry(
                        s, "post", url, json=payload_plain, timeout=10
                    )
                    result.append(resp_retry)
                    if resp_retry.status_code != 200:
                        logger.warning(
                            "Telegram plain text retry also failed %s: %s",
                            resp_retry.status_code,
                            resp_retry.text[:200],
                        )
                except requests.RequestException as exc_retry:
                    logger.warning("Failed to send Telegram plain text retry: %s", exc_retry)
            elif resp.status_code != 200:
                logger.warning(
                    "Telegram API returned %s: %s",
                    resp.status_code,
                    resp.text[:200],
                )
        except requests.RequestException as exc:
            logger.warning("Failed to send Telegram reply: %s", exc)
    return result


def send_reply_markdown(
    token: str,
    chat_id: str,
    body: str,
    reply_to_message_id: int | None = None,
    highlight_max: bool = False,
    thread_id: int | None = None,
    session: requests.Session | None = None,
) -> list[requests.Response]:
    """Send a markdown reply with text/table segmentation and image support.

    Tables are rendered as PNG images via pandoc + wkhtmltoimage.
    Falls back to code blocks if rendering tools are not available.
    """
    body = (body or "").strip() or "(no response)"
    segments = split_body_into_segments(body)
    all_responses: list[requests.Response] = []
    max_prefix_len = 12
    first_message = True

    for segment in segments:
        if segment.kind == "text":
            content = segment.content
            if not content.strip():
                continue
            formatted = format_markdown(content)
            parts = split_text(formatted, limit=TELEGRAM_TEXT_LIMIT - max_prefix_len)
            reply_id = reply_to_message_id if first_message else None
            all_responses.extend(
                send_text_parts(
                    token,
                    chat_id,
                    parts,
                    add_part_prefix=len(parts) > 1,
                    reply_to_message_id=reply_id,
                    thread_id=thread_id,
                    session=session,
                )
            )
            first_message = False
        elif segment.kind == "table":
            content = segment.content
            photo_sent = False
            try:
                png_path = md_table_to_png(content, output_path=None, highlight_max=highlight_max)
                photo_resp = send_photo(
                    token,
                    chat_id,
                    png_path,
                    reply_to_message_id=reply_to_message_id if first_message else None,
                    thread_id=thread_id,
                    session=session,
                )
                if photo_resp is not None and photo_resp.status_code == 200:
                    all_responses.append(photo_resp)
                    photo_sent = True
                elif photo_resp is not None:
                    logger.warning(
                        "sendPhoto failed (%s), falling back to code block", photo_resp.status_code
                    )
            except (RuntimeError, OSError) as exc:
                logger.warning("Table-to-PNG failed, falling back to code block: %s", exc)
            if not photo_sent:
                code_block = f"```\n{content}\n```"
                parts = split_text(code_block, limit=TELEGRAM_TEXT_LIMIT - max_prefix_len)
                reply_id = reply_to_message_id if first_message else None
                all_responses.extend(
                    send_text_parts(
                        token,
                        chat_id,
                        parts,
                        add_part_prefix=len(parts) > 1,
                        reply_to_message_id=reply_id,
                        thread_id=thread_id,
                        session=session,
                    )
                )
            first_message = False
        elif segment.kind == "image":
            if segment.image is None:
                continue
            image_ref = segment.image
            caption = image_ref.caption or image_ref.path.name
            photo_resp = send_photo(
                token=token,
                chat_id=chat_id,
                png_path=image_ref.path,
                caption=caption,
                delete_after_send=False,
                reply_to_message_id=reply_to_message_id if first_message else None,
                thread_id=thread_id,
                session=session,
            )
            if photo_resp is not None:
                all_responses.append(photo_resp)
            first_message = False

    if first_message:
        all_responses.extend(
            send_text_parts(
                token,
                chat_id,
                [escape_markdownv2(body)],
                add_part_prefix=False,
                reply_to_message_id=reply_to_message_id,
                thread_id=thread_id,
                session=session,
            )
        )

    return all_responses


def get_updates(
    token: str,
    chat_id: str,
    offset: int,
    timeout_sec: int = 30,
    session: requests.Session | None = None,
) -> tuple[int, list[tuple[str, int, int | None]]]:
    """Long-poll getUpdates for the given chat_id."""
    next_offset, all_msgs = get_all_updates(token, offset, timeout_sec, session=session)
    messages = [(text, mid, uid) for cid, text, mid, uid in all_msgs if str(cid) == str(chat_id)]
    return (next_offset, messages)


def get_all_updates(
    token: str,
    offset: int,
    timeout_sec: int = 30,
    session: requests.Session | None = None,
) -> tuple[int, list[tuple[str, str, int, int | None]]]:
    """Long-poll getUpdates for all chats."""
    s = session or make_session()
    url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout={timeout_sec}"
    next_offset = offset
    messages: list[tuple[str, str, int, int | None]] = []
    try:
        resp = _request_with_retry(s, "get", url, timeout=timeout_sec + 10)
        if resp.status_code != 200:
            return (next_offset, [])
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as exc:
        logger.warning("getUpdates failed: %s", exc)
        return (next_offset, [])
    for upd in data.get("result", []):
        next_offset = max(next_offset, upd.get("update_id", 0) + 1)
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            continue
        chat_id_str = str(msg.get("chat", {}).get("id", ""))
        if not chat_id_str:
            continue
        text = (msg.get("text") or "").strip()
        if text:
            message_id = msg.get("message_id", 0)
            user_id = (msg.get("from") or {}).get("id")
            messages.append((chat_id_str, text, message_id, user_id))
    return (next_offset, messages)


def set_message_reaction(
    token: str,
    chat_id: str,
    message_id: int,
    emoji: str = "\U0001f440",
    session: requests.Session | None = None,
) -> None:
    """Set a reaction (e.g. eyes emoji) on a message. Silently no-ops on failure."""
    s = session or make_session()
    url = f"https://api.telegram.org/bot{token}/setMessageReaction"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reaction": [{"type": "emoji", "emoji": emoji}],
    }
    try:
        resp = _request_with_retry(s, "post", url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.warning(
                "setMessageReaction returned %s: %s",
                resp.status_code,
                resp.text[:200],
            )
    except requests.RequestException as exc:
        logger.warning("setMessageReaction failed: %s", exc)


def fetch_bot_username(token: str, session: requests.Session | None = None) -> str | None:
    """Call Telegram getMe API once to retrieve the bot username."""
    s = session or make_session()
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        resp = _request_with_retry(s, "get", url, timeout=10)
        if resp.status_code != 200:
            logger.warning("getMe returned %s: %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        username = data.get("result", {}).get("username")
        if username:
            logger.info("Bot username from getMe: @%s", username)
        return username
    except (requests.RequestException, json.JSONDecodeError) as exc:
        logger.warning("getMe failed: %s", exc)
        return None
