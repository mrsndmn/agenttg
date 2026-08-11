"""Telegram HTTP API calls: send messages, photos, videos, reactions, and poll updates."""

from __future__ import annotations

import json
import logging
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
from .rich_message import rich_table_within_limits, send_rich_markdown
from .table_modes import table_render_chain
from .table_to_png import md_table_to_png
from .transport import _request_with_retry, make_session

logger = logging.getLogger("agenttg")

#: Room reserved in every text part for the optional "[i/N]" part prefix.
_MAX_PREFIX_LEN = 12


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


def send_video(
    token: str,
    chat_id: str,
    video_path: Path,
    caption: str | None = None,
    delete_after_send: bool = True,
    reply_to_message_id: int | None = None,
    thread_id: int | None = None,
    session: requests.Session | None = None,
) -> requests.Response | None:
    """Send a video file to the chat. Returns response or None on failure."""
    s = session or make_session()
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    data: dict[str, object] = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption[:1024]
    if reply_to_message_id is not None:
        data["reply_to_message_id"] = reply_to_message_id
    if thread_id is not None:
        data["message_thread_id"] = thread_id
    try:
        with open(video_path, "rb") as f:
            resp = _request_with_retry(
                s,
                "post",
                url,
                data=data,
                files={"video": f},
                timeout=120,
            )
        if resp.status_code != 200:
            logger.warning(
                "Telegram sendVideo returned %s: %s",
                resp.status_code,
                resp.text[:200],
            )
        return resp
    except (requests.RequestException, OSError) as exc:
        logger.warning("Failed to send Telegram video: %s", exc)
        return None
    finally:
        if delete_after_send and video_path.exists():
            with suppress(OSError):
                video_path.unlink()


def send_document(
    token: str,
    chat_id: str,
    file_path: Path,
    caption: str | None = None,
    delete_after_send: bool = True,
    reply_to_message_id: int | None = None,
    thread_id: int | None = None,
    session: requests.Session | None = None,
) -> requests.Response | None:
    """Send a file as a document to the chat. Returns response or None on failure."""
    s = session or make_session()
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    data: dict[str, object] = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption[:1024]
    if reply_to_message_id is not None:
        data["reply_to_message_id"] = reply_to_message_id
    if thread_id is not None:
        data["message_thread_id"] = thread_id
    try:
        with open(file_path, "rb") as f:
            resp = _request_with_retry(
                s,
                "post",
                url,
                data=data,
                files={"document": f},
                timeout=120,
            )
        if resp.status_code != 200:
            logger.warning(
                "Telegram sendDocument returned %s: %s",
                resp.status_code,
                resp.text[:200],
            )
        return resp
    except (requests.RequestException, OSError) as exc:
        logger.warning("Failed to send Telegram document: %s", exc)
        return None
    finally:
        if delete_after_send and file_path.exists():
            with suppress(OSError):
                file_path.unlink()


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
                    resp_retry = _request_with_retry(s, "post", url, json=payload_plain, timeout=10)
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
                    resp_retry = _request_with_retry(s, "post", url, json=payload_plain, timeout=10)
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


def _send_table_as_code_block(
    token: str,
    chat_id: str,
    content: str,
    reply_to_message_id: int | None,
    thread_id: int | None,
    session: requests.Session | None,
) -> list[requests.Response]:
    """Send a markdown table verbatim inside a fixed-width code block."""
    code_block = f"```\n{content}\n```"
    parts = split_text(code_block, limit=TELEGRAM_TEXT_LIMIT - _MAX_PREFIX_LEN)
    return send_text_parts(
        token,
        chat_id,
        parts,
        add_part_prefix=len(parts) > 1,
        reply_to_message_id=reply_to_message_id,
        thread_id=thread_id,
        session=session,
    )


def _send_table_as_photo(
    token: str,
    chat_id: str,
    content: str,
    reply_to_message_id: int | None,
    thread_id: int | None,
    session: requests.Session | None,
    highlight_max: bool,
) -> list[requests.Response] | None:
    """Render a table to PNG and send it. Returns None when the render/send failed."""
    try:
        png_path = md_table_to_png(content, output_path=None, highlight_max=highlight_max)
    except (RuntimeError, OSError) as exc:
        logger.warning("Table-to-PNG failed: %s", exc)
        return None
    resp = send_photo(
        token,
        chat_id,
        png_path,
        reply_to_message_id=reply_to_message_id,
        thread_id=thread_id,
        session=session,
    )
    if resp is None or resp.status_code != 200:
        logger.warning("sendPhoto failed (%s)", "no response" if resp is None else resp.status_code)
        return None
    return [resp]


def _send_table_as_rich(
    token: str,
    chat_id: str,
    content: str,
    reply_to_message_id: int | None,
    thread_id: int | None,
    session: requests.Session | None,
) -> list[requests.Response] | None:
    """Send a table as a native rich message. Returns None when it was not sent."""
    fits, reason = rich_table_within_limits(content)
    if not fits:
        logger.warning("Table exceeds rich message limits (%s)", reason)
        return None
    resp = send_rich_markdown(
        token,
        chat_id,
        content,
        reply_to_message_id=reply_to_message_id,
        thread_id=thread_id,
        session=session,
    )
    if resp is None or resp.status_code != 200:
        return None
    return [resp]


def _send_table_segment(
    token: str,
    chat_id: str,
    content: str,
    reply_to_message_id: int | None,
    thread_id: int | None,
    session: requests.Session | None,
    highlight_max: bool,
    table_mode: str | None,
) -> list[requests.Response]:
    """Deliver one table segment, walking the configured render chain.

    The first renderer that succeeds wins; ``code`` terminates every chain, so a
    table is never dropped because pandoc is missing or the rich API refused it.
    """
    for mode in table_render_chain(table_mode):
        if mode == "code":
            return _send_table_as_code_block(
                token, chat_id, content, reply_to_message_id, thread_id, session
            )
        if mode == "image":
            sent = _send_table_as_photo(
                token,
                chat_id,
                content,
                reply_to_message_id,
                thread_id,
                session,
                highlight_max,
            )
        else:
            sent = _send_table_as_rich(
                token, chat_id, content, reply_to_message_id, thread_id, session
            )
        if sent is not None:
            return sent
        logger.warning("Table render mode %r failed, trying the next renderer", mode)
    return []


def send_reply_markdown(
    token: str,
    chat_id: str,
    body: str,
    reply_to_message_id: int | None = None,
    highlight_max: bool = False,
    thread_id: int | None = None,
    session: requests.Session | None = None,
    workdir: Path | None = None,
    table_mode: str | None = None,
) -> list[requests.Response]:
    """Send a markdown reply with text/table segmentation and media support.

    Each table is sent as its own message, rendered according to *table_mode*
    (``image``, ``rich``/``table``, or ``code``; default from
    ``AGENTTG_TABLE_MODE``, see :mod:`agenttg.table_modes`), falling through to
    the next renderer in the chain on failure. A single table overrides that with
    a ``<!-- fmt=... -->`` directive on the line above it.
    *workdir* overrides ``Path.cwd()`` when resolving relative media paths.
    """
    body = (body or "").strip() or "(no response)"
    segments = split_body_into_segments(body, workdir=workdir)
    all_responses: list[requests.Response] = []
    max_prefix_len = _MAX_PREFIX_LEN
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
            all_responses.extend(
                _send_table_segment(
                    token,
                    chat_id,
                    segment.content,
                    reply_to_message_id if first_message else None,
                    thread_id,
                    session,
                    highlight_max,
                    # A "<!-- fmt=... -->" directive on this table wins over the
                    # caller's mode, which in turn wins over the environment.
                    segment.table_mode or table_mode,
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
        elif segment.kind == "video":
            if segment.image is None:
                continue
            video_ref = segment.image
            caption = video_ref.caption or video_ref.path.name
            video_resp = send_video(
                token=token,
                chat_id=chat_id,
                video_path=video_ref.path,
                caption=caption,
                delete_after_send=False,
                reply_to_message_id=reply_to_message_id if first_message else None,
                thread_id=thread_id,
                session=session,
            )
            if video_resp is not None:
                all_responses.append(video_resp)
            first_message = False
        elif segment.kind == "document":
            if segment.image is None:
                continue
            doc_ref = segment.image
            caption = doc_ref.caption or doc_ref.path.name
            doc_resp = send_document(
                token=token,
                chat_id=chat_id,
                file_path=doc_ref.path,
                caption=caption,
                delete_after_send=False,
                reply_to_message_id=reply_to_message_id if first_message else None,
                thread_id=thread_id,
                session=session,
            )
            if doc_resp is not None:
                all_responses.append(doc_resp)
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
