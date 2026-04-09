"""Unit tests for agenttg API functions with mocked HTTP requests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

import agenttg


def _make_ok_response(data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.text = json.dumps(data or {"ok": True})
    resp.json.return_value = data or {"ok": True}
    return resp


def _make_error_response(code: int = 400, text: str = "Bad Request") -> MagicMock:
    resp = MagicMock()
    resp.status_code = code
    resp.text = text
    resp.json.return_value = {"ok": False, "description": text}
    return resp


@pytest.fixture()
def mock_session():
    """Return a mock requests.Session with .post and .get mocked."""
    s = MagicMock(spec=requests.Session)
    s.post.return_value = _make_ok_response()
    s.get.return_value = _make_ok_response()
    return s


# ---------------------------------------------------------------------------
# send_reply
# ---------------------------------------------------------------------------


def test_send_reply_sends_plain_text(mock_session):
    result = agenttg.send_reply("TOKEN", "123", "Hello!", session=mock_session)
    assert len(result) == 1
    call_kwargs = mock_session.post.call_args
    payload = call_kwargs[1]["json"]
    assert payload["chat_id"] == "123"
    assert payload["text"] == "Hello!"
    assert "parse_mode" not in payload


def test_send_reply_splits_long_text(mock_session):
    text = "x" * 5000
    result = agenttg.send_reply("TOKEN", "123", text, session=mock_session)
    assert len(result) == 2


def test_send_reply_with_reply_to(mock_session):
    agenttg.send_reply("TOKEN", "123", "Hi", reply_to_message_id=42, session=mock_session)
    payload = mock_session.post.call_args[1]["json"]
    assert payload["reply_to_message_id"] == 42


def test_send_reply_with_thread_id(mock_session):
    agenttg.send_reply("TOKEN", "123", "Hi", thread_id=99, session=mock_session)
    payload = mock_session.post.call_args[1]["json"]
    assert payload["message_thread_id"] == 99


def test_send_reply_thread_id_on_all_parts(mock_session):
    text = "x" * 5000
    agenttg.send_reply("TOKEN", "123", text, thread_id=99, session=mock_session)
    for call in mock_session.post.call_args_list:
        payload = call[1]["json"]
        assert payload["message_thread_id"] == 99


# ---------------------------------------------------------------------------
# send_reply_html
# ---------------------------------------------------------------------------


def test_send_reply_html_sends_html(mock_session):
    result = agenttg.send_reply_html("TOKEN", "123", "<b>Bold</b>", session=mock_session)
    assert len(result) == 1
    payload = mock_session.post.call_args[1]["json"]
    assert payload["parse_mode"] == "HTML"
    assert payload["text"] == "<b>Bold</b>"


def test_send_reply_html_retries_on_parse_error(mock_session):
    error_resp = _make_error_response(400, "can't parse entities")
    ok_resp = _make_ok_response()
    mock_session.post.side_effect = [error_resp, ok_resp]
    result = agenttg.send_reply_html("TOKEN", "123", "<broken>", session=mock_session)
    assert len(result) == 2
    # Second call should be without parse_mode
    second_payload = mock_session.post.call_args_list[1][1]["json"]
    assert "parse_mode" not in second_payload


def test_send_reply_html_empty_returns_empty(mock_session):
    result = agenttg.send_reply_html("TOKEN", "123", "   ", session=mock_session)
    assert result == []
    mock_session.post.assert_not_called()


# ---------------------------------------------------------------------------
# send_text_parts
# ---------------------------------------------------------------------------


def test_send_reply_html_with_thread_id(mock_session):
    agenttg.send_reply_html("TOKEN", "123", "<b>Bold</b>", thread_id=55, session=mock_session)
    payload = mock_session.post.call_args[1]["json"]
    assert payload["message_thread_id"] == 55


def test_send_text_parts_with_thread_id(mock_session):
    agenttg.send_text_parts(
        "TOKEN", "123", ["p1", "p2"], add_part_prefix=False, thread_id=77, session=mock_session
    )
    for call in mock_session.post.call_args_list:
        payload = call[1]["json"]
        assert payload["message_thread_id"] == 77


def test_send_photo_with_thread_id(mock_session, tmp_path):
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    agenttg.send_photo(
        "TOKEN", "123", img_path, thread_id=88, delete_after_send=False, session=mock_session
    )
    data = mock_session.post.call_args[1]["data"]
    assert data["message_thread_id"] == 88


def test_send_text_parts_with_prefix(mock_session):
    result = agenttg.send_text_parts(
        "TOKEN", "123", ["part1", "part2"], add_part_prefix=True, session=mock_session
    )
    assert len(result) == 2
    first_payload = mock_session.post.call_args_list[0][1]["json"]
    assert first_payload["parse_mode"] == "MarkdownV2"
    assert "[1/2]" in first_payload["text"] or "\\[1/2\\]" in first_payload["text"]


def test_send_text_parts_retries_without_formatting_on_parse_error(mock_session):
    error_resp = _make_error_response(400, "can't parse entities in MarkdownV2")
    ok_resp = _make_ok_response()
    mock_session.post.side_effect = [error_resp, ok_resp]
    result = agenttg.send_text_parts(
        "TOKEN", "123", ["hello"], add_part_prefix=False, session=mock_session
    )
    assert len(result) == 2


# ---------------------------------------------------------------------------
# send_photo
# ---------------------------------------------------------------------------


def test_send_photo(mock_session, tmp_path):
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    resp = agenttg.send_photo(
        "TOKEN", "123", img_path, caption="Test", delete_after_send=False, session=mock_session
    )
    assert resp is not None
    assert resp.status_code == 200
    call_args = mock_session.post.call_args
    assert call_args[1]["data"]["chat_id"] == "123"
    assert call_args[1]["data"]["caption"] == "Test"


def test_send_photo_deletes_after_send(mock_session, tmp_path):
    img_path = tmp_path / "delete_me.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    agenttg.send_photo("TOKEN", "123", img_path, delete_after_send=True, session=mock_session)
    assert not img_path.exists()


# ---------------------------------------------------------------------------
# send_reply_markdown
# ---------------------------------------------------------------------------


@patch("agenttg.api.md_table_to_png")
def test_send_reply_markdown_text_only(mock_table, mock_session):
    result = agenttg.send_reply_markdown("TOKEN", "123", "Hello **world**", session=mock_session)
    assert len(result) >= 1
    mock_table.assert_not_called()


@patch("agenttg.api.md_table_to_png")
def test_send_reply_markdown_with_table_fallback(mock_table, mock_session):
    mock_table.side_effect = RuntimeError("pandoc not found")
    body = "Intro\n| A | B |\n|---|---|\n| 1 | 2 |\nOutro"
    result = agenttg.send_reply_markdown("TOKEN", "123", body, session=mock_session)
    assert len(result) >= 1


# ---------------------------------------------------------------------------
# get_updates
# ---------------------------------------------------------------------------


def test_get_updates_parses_response(mock_session):
    mock_session.get.return_value = _make_ok_response(
        {
            "ok": True,
            "result": [
                {
                    "update_id": 100,
                    "message": {
                        "message_id": 1,
                        "chat": {"id": 123},
                        "from": {"id": 456},
                        "text": "hello",
                    },
                }
            ],
        }
    )
    offset, msgs = agenttg.get_updates("TOKEN", "123", offset=0, session=mock_session)
    assert offset == 101
    assert len(msgs) == 1
    assert msgs[0] == ("hello", 1, 456)


def test_get_updates_filters_by_chat_id(mock_session):
    mock_session.get.return_value = _make_ok_response(
        {
            "ok": True,
            "result": [
                {
                    "update_id": 100,
                    "message": {
                        "message_id": 1,
                        "chat": {"id": 999},
                        "from": {"id": 456},
                        "text": "wrong chat",
                    },
                }
            ],
        }
    )
    offset, msgs = agenttg.get_updates("TOKEN", "123", offset=0, session=mock_session)
    assert offset == 101
    assert len(msgs) == 0


# ---------------------------------------------------------------------------
# get_all_updates
# ---------------------------------------------------------------------------


def test_get_all_updates(mock_session):
    mock_session.get.return_value = _make_ok_response(
        {
            "ok": True,
            "result": [
                {
                    "update_id": 200,
                    "message": {
                        "message_id": 5,
                        "chat": {"id": 111},
                        "from": {"id": 222},
                        "text": "msg1",
                    },
                },
                {
                    "update_id": 201,
                    "message": {
                        "message_id": 6,
                        "chat": {"id": 333},
                        "from": {"id": 444},
                        "text": "msg2",
                    },
                },
            ],
        }
    )
    offset, msgs = agenttg.get_all_updates("TOKEN", offset=0, session=mock_session)
    assert offset == 202
    assert len(msgs) == 2


# ---------------------------------------------------------------------------
# set_message_reaction
# ---------------------------------------------------------------------------


def test_set_message_reaction(mock_session):
    agenttg.set_message_reaction(
        "TOKEN", "123", message_id=42, emoji="\U0001f44d", session=mock_session
    )
    payload = mock_session.post.call_args[1]["json"]
    assert payload["chat_id"] == "123"
    assert payload["message_id"] == 42
    assert payload["reaction"][0]["emoji"] == "\U0001f44d"


# ---------------------------------------------------------------------------
# fetch_bot_username
# ---------------------------------------------------------------------------


def test_fetch_bot_username(mock_session):
    mock_session.get.return_value = _make_ok_response(
        {
            "ok": True,
            "result": {"id": 123, "is_bot": True, "username": "test_bot"},
        }
    )
    username = agenttg.fetch_bot_username("TOKEN", session=mock_session)
    assert username == "test_bot"


def test_fetch_bot_username_failure(mock_session):
    mock_session.get.return_value = _make_error_response(401, "Unauthorized")
    username = agenttg.fetch_bot_username("BAD_TOKEN", session=mock_session)
    assert username is None


# ---------------------------------------------------------------------------
# _request_with_retry
# ---------------------------------------------------------------------------


@patch("agenttg.api.time.sleep")
def test_request_with_retry_retries_on_connection_error(mock_sleep):
    """Retry should be attempted on transient connection errors."""
    import agenttg.api as api

    session = MagicMock(spec=requests.Session)
    session.post.side_effect = [
        requests.ConnectionError("SSL EOF"),
        _make_ok_response(),
    ]

    resp = api._request_with_retry(session, "post", "http://example.com", timeout=5)
    assert resp.status_code == 200
    assert session.post.call_count == 2


@patch("agenttg.api.time.sleep")
def test_request_with_retry_raises_after_max_retries(mock_sleep):
    """Should raise after exhausting all retry attempts."""
    import agenttg.api as api

    session = MagicMock(spec=requests.Session)
    session.post.side_effect = requests.ConnectionError("SSL EOF")

    with pytest.raises(requests.ConnectionError):
        api._request_with_retry(session, "post", "http://example.com", timeout=5)
    assert session.post.call_count == api._MAX_RETRIES
