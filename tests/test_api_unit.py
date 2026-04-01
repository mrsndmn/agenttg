"""Unit tests for agenttg API functions with mocked HTTP requests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

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


# ---------------------------------------------------------------------------
# send_reply
# ---------------------------------------------------------------------------


@patch("agenttg.api.requests.post")
def test_send_reply_sends_plain_text(mock_post):
    mock_post.return_value = _make_ok_response()
    result = agenttg.send_reply("TOKEN", "123", "Hello!")
    assert len(result) == 1
    call_kwargs = mock_post.call_args
    payload = call_kwargs[1]["json"]
    assert payload["chat_id"] == "123"
    assert payload["text"] == "Hello!"
    assert "parse_mode" not in payload


@patch("agenttg.api.requests.post")
def test_send_reply_splits_long_text(mock_post):
    mock_post.return_value = _make_ok_response()
    text = "x" * 5000
    result = agenttg.send_reply("TOKEN", "123", text)
    assert len(result) == 2


@patch("agenttg.api.requests.post")
def test_send_reply_with_reply_to(mock_post):
    mock_post.return_value = _make_ok_response()
    agenttg.send_reply("TOKEN", "123", "Hi", reply_to_message_id=42)
    payload = mock_post.call_args[1]["json"]
    assert payload["reply_to_message_id"] == 42


# ---------------------------------------------------------------------------
# send_reply_html
# ---------------------------------------------------------------------------


@patch("agenttg.api.requests.post")
def test_send_reply_html_sends_html(mock_post):
    mock_post.return_value = _make_ok_response()
    result = agenttg.send_reply_html("TOKEN", "123", "<b>Bold</b>")
    assert len(result) == 1
    payload = mock_post.call_args[1]["json"]
    assert payload["parse_mode"] == "HTML"
    assert payload["text"] == "<b>Bold</b>"


@patch("agenttg.api.requests.post")
def test_send_reply_html_retries_on_parse_error(mock_post):
    error_resp = _make_error_response(400, "can't parse entities")
    ok_resp = _make_ok_response()
    mock_post.side_effect = [error_resp, ok_resp]
    result = agenttg.send_reply_html("TOKEN", "123", "<broken>")
    assert len(result) == 2
    # Second call should be without parse_mode
    second_payload = mock_post.call_args_list[1][1]["json"]
    assert "parse_mode" not in second_payload


@patch("agenttg.api.requests.post")
def test_send_reply_html_empty_returns_empty(mock_post):
    result = agenttg.send_reply_html("TOKEN", "123", "   ")
    assert result == []
    mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# send_text_parts
# ---------------------------------------------------------------------------


@patch("agenttg.api.requests.post")
def test_send_text_parts_with_prefix(mock_post):
    mock_post.return_value = _make_ok_response()
    result = agenttg.send_text_parts("TOKEN", "123", ["part1", "part2"], add_part_prefix=True)
    assert len(result) == 2
    first_payload = mock_post.call_args_list[0][1]["json"]
    assert first_payload["parse_mode"] == "MarkdownV2"
    assert "[1/2]" in first_payload["text"] or "\\[1/2\\]" in first_payload["text"]


@patch("agenttg.api.requests.post")
def test_send_text_parts_retries_without_formatting_on_parse_error(mock_post):
    error_resp = _make_error_response(400, "can't parse entities in MarkdownV2")
    ok_resp = _make_ok_response()
    mock_post.side_effect = [error_resp, ok_resp]
    result = agenttg.send_text_parts("TOKEN", "123", ["hello"], add_part_prefix=False)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# send_photo
# ---------------------------------------------------------------------------


@patch("agenttg.api.requests.post")
def test_send_photo(mock_post, tmp_path):
    mock_post.return_value = _make_ok_response()
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    resp = agenttg.send_photo("TOKEN", "123", img_path, caption="Test", delete_after_send=False)
    assert resp is not None
    assert resp.status_code == 200
    call_args = mock_post.call_args
    assert call_args[1]["data"]["chat_id"] == "123"
    assert call_args[1]["data"]["caption"] == "Test"


@patch("agenttg.api.requests.post")
def test_send_photo_deletes_after_send(mock_post, tmp_path):
    mock_post.return_value = _make_ok_response()
    img_path = tmp_path / "delete_me.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    agenttg.send_photo("TOKEN", "123", img_path, delete_after_send=True)
    assert not img_path.exists()


# ---------------------------------------------------------------------------
# send_reply_markdown
# ---------------------------------------------------------------------------


@patch("agenttg.api.md_table_to_png")
@patch("agenttg.api.requests.post")
def test_send_reply_markdown_text_only(mock_post, mock_table):
    mock_post.return_value = _make_ok_response()
    result = agenttg.send_reply_markdown("TOKEN", "123", "Hello **world**")
    assert len(result) >= 1
    mock_table.assert_not_called()


@patch("agenttg.api.md_table_to_png")
@patch("agenttg.api.requests.post")
def test_send_reply_markdown_with_table_fallback(mock_post, mock_table):
    mock_table.side_effect = RuntimeError("pandoc not found")
    mock_post.return_value = _make_ok_response()
    body = "Intro\n| A | B |\n|---|---|\n| 1 | 2 |\nOutro"
    result = agenttg.send_reply_markdown("TOKEN", "123", body)
    assert len(result) >= 1


# ---------------------------------------------------------------------------
# get_updates
# ---------------------------------------------------------------------------


@patch("agenttg.api.requests.get")
def test_get_updates_parses_response(mock_get):
    mock_get.return_value = _make_ok_response(
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
    offset, msgs = agenttg.get_updates("TOKEN", "123", offset=0)
    assert offset == 101
    assert len(msgs) == 1
    assert msgs[0] == ("hello", 1, 456)


@patch("agenttg.api.requests.get")
def test_get_updates_filters_by_chat_id(mock_get):
    mock_get.return_value = _make_ok_response(
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
    offset, msgs = agenttg.get_updates("TOKEN", "123", offset=0)
    assert offset == 101
    assert len(msgs) == 0


# ---------------------------------------------------------------------------
# get_all_updates
# ---------------------------------------------------------------------------


@patch("agenttg.api.requests.get")
def test_get_all_updates(mock_get):
    mock_get.return_value = _make_ok_response(
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
    offset, msgs = agenttg.get_all_updates("TOKEN", offset=0)
    assert offset == 202
    assert len(msgs) == 2


# ---------------------------------------------------------------------------
# set_message_reaction
# ---------------------------------------------------------------------------


@patch("agenttg.api.requests.post")
def test_set_message_reaction(mock_post):
    mock_post.return_value = _make_ok_response()
    agenttg.set_message_reaction("TOKEN", "123", message_id=42, emoji="\U0001f44d")
    payload = mock_post.call_args[1]["json"]
    assert payload["chat_id"] == "123"
    assert payload["message_id"] == 42
    assert payload["reaction"][0]["emoji"] == "\U0001f44d"


# ---------------------------------------------------------------------------
# fetch_bot_username
# ---------------------------------------------------------------------------


@patch("agenttg.api.requests.get")
def test_fetch_bot_username(mock_get):
    mock_get.return_value = _make_ok_response(
        {
            "ok": True,
            "result": {"id": 123, "is_bot": True, "username": "test_bot"},
        }
    )
    username = agenttg.fetch_bot_username("TOKEN")
    assert username == "test_bot"


@patch("agenttg.api.requests.get")
def test_fetch_bot_username_failure(mock_get):
    mock_get.return_value = _make_error_response(401, "Unauthorized")
    username = agenttg.fetch_bot_username("BAD_TOKEN")
    assert username is None
