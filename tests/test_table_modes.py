"""Unit tests for table rendering modes, rich messages, and the fallback chain."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

import agenttg
from agenttg import rich_message, table_modes

TABLE = "| A | B |\n|---|---|\n| 1 | 2 |"
BODY_WITH_TABLE = f"Intro\n{TABLE}\nOutro"


def _ok_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.text = json.dumps({"ok": True})
    resp.json.return_value = {"ok": True}
    return resp


def _error_response(code: int = 400, text: str = "Bad Request") -> MagicMock:
    resp = MagicMock()
    resp.status_code = code
    resp.text = text
    resp.json.return_value = {"ok": False, "description": text}
    return resp


@pytest.fixture()
def mock_session():
    s = MagicMock(spec=requests.Session)
    s.post.return_value = _ok_response()
    s.get.return_value = _ok_response()
    return s


@pytest.fixture(autouse=True)
def _clear_mode_env(monkeypatch):
    monkeypatch.delenv(table_modes.TABLE_MODE_ENV, raising=False)


def _posted_methods(mock_session) -> list[str]:
    """Return the Telegram method name of every POST the session received."""
    return [call.args[0].rsplit("/", 1)[-1] for call in mock_session.post.call_args_list]


# ---------------------------------------------------------------------------
# mode resolution
# ---------------------------------------------------------------------------


def test_default_mode_is_image():
    assert agenttg.resolve_table_mode() == "image"
    assert agenttg.table_render_chain() == ("image", "rich", "code")


def test_env_var_selects_mode(monkeypatch):
    monkeypatch.setenv(table_modes.TABLE_MODE_ENV, "rich")
    assert agenttg.resolve_table_mode() == "rich"
    assert agenttg.table_render_chain() == ("rich", "image", "code")


def test_env_var_is_case_and_space_insensitive(monkeypatch):
    monkeypatch.setenv(table_modes.TABLE_MODE_ENV, "  RICH ")
    assert agenttg.resolve_table_mode() == "rich"


def test_explicit_mode_beats_env(monkeypatch):
    monkeypatch.setenv(table_modes.TABLE_MODE_ENV, "rich")
    assert agenttg.resolve_table_mode("image") == "image"


def test_unknown_mode_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(table_modes.TABLE_MODE_ENV, "hologram")
    assert agenttg.resolve_table_mode() == "image"
    assert agenttg.resolve_table_mode("nonsense") == "image"


def test_code_mode_chain_is_terminal():
    assert agenttg.table_render_chain("code") == ("code",)


# ---------------------------------------------------------------------------
# rich message limits
# ---------------------------------------------------------------------------


def test_table_dimensions_ignores_delimiter_row():
    assert agenttg.table_dimensions(TABLE) == (2, 2)


def test_table_dimensions_ignores_escaped_pipes():
    table = "| A | B |\n|---|---|\n| a \\| b | 2 |"
    assert agenttg.table_dimensions(table) == (2, 2)


def test_small_table_is_within_limits():
    fits, reason = agenttg.rich_table_within_limits(TABLE)
    assert fits is True
    assert reason == ""


def test_too_many_columns_is_rejected():
    cols = agenttg.RICH_TABLE_COLUMN_LIMIT + 1
    header = "|" + "|".join(f" c{i} " for i in range(cols)) + "|"
    delim = "|" + "|".join("---" for _ in range(cols)) + "|"
    fits, reason = agenttg.rich_table_within_limits(f"{header}\n{delim}")
    assert fits is False
    assert "columns" in reason


def test_too_many_rows_is_rejected():
    rows = "\n".join("| a | b |" for _ in range(agenttg.RICH_BLOCK_LIMIT))
    fits, reason = agenttg.rich_table_within_limits(f"| A | B |\n|---|---|\n{rows}")
    assert fits is False
    assert "rows" in reason


def test_too_long_text_is_rejected():
    fits, reason = agenttg.rich_table_within_limits("| A |\n|---|\n" + "x" * 40000)
    assert fits is False
    assert "chars" in reason


# ---------------------------------------------------------------------------
# send_rich_markdown payload
# ---------------------------------------------------------------------------


def test_send_rich_markdown_payload(mock_session):
    agenttg.send_rich_markdown("TOKEN", "123", TABLE, session=mock_session)
    url = mock_session.post.call_args.args[0]
    payload = mock_session.post.call_args.kwargs["json"]
    assert url.endswith("/sendRichMessage")
    assert payload["chat_id"] == "123"
    assert payload["rich_message"] == {"markdown": TABLE}
    assert "reply_parameters" not in payload
    assert "message_thread_id" not in payload


def test_send_rich_markdown_reply_and_topic(mock_session):
    agenttg.send_rich_markdown(
        "TOKEN", "123", TABLE, reply_to_message_id=42, thread_id=7, session=mock_session
    )
    payload = mock_session.post.call_args.kwargs["json"]
    assert payload["reply_parameters"] == {
        "message_id": 42,
        "allow_sending_without_reply": True,
    }
    assert payload["message_thread_id"] == 7


def test_send_rich_markdown_returns_none_on_transport_error(mock_session):
    mock_session.post.side_effect = requests.ConnectionError("boom")
    assert agenttg.send_rich_markdown("TOKEN", "123", TABLE, session=mock_session) is None


# ---------------------------------------------------------------------------
# render chain inside send_reply_markdown
# ---------------------------------------------------------------------------


@patch("agenttg.api.md_table_to_png")
def test_rich_mode_sends_rich_message_without_rendering_png(mock_png, mock_session):
    agenttg.send_reply_markdown(
        "TOKEN", "123", BODY_WITH_TABLE, session=mock_session, table_mode="rich"
    )
    mock_png.assert_not_called()
    assert "sendRichMessage" in _posted_methods(mock_session)


@patch("agenttg.api.md_table_to_png")
def test_table_stays_a_separate_message(mock_png, mock_session):
    agenttg.send_reply_markdown(
        "TOKEN", "123", BODY_WITH_TABLE, session=mock_session, table_mode="rich"
    )
    methods = _posted_methods(mock_session)
    # Intro text, the table on its own, then the outro text.
    assert methods == ["sendMessage", "sendRichMessage", "sendMessage"]
    intro = mock_session.post.call_args_list[0].kwargs["json"]["text"]
    assert "|" not in intro


@patch("agenttg.api.send_photo")
@patch("agenttg.api.md_table_to_png")
def test_image_mode_prefers_photo(mock_png, mock_photo, mock_session, tmp_path):
    mock_png.return_value = tmp_path / "t.png"
    mock_photo.return_value = _ok_response()
    agenttg.send_reply_markdown(
        "TOKEN", "123", BODY_WITH_TABLE, session=mock_session, table_mode="image"
    )
    mock_photo.assert_called_once()
    assert "sendRichMessage" not in _posted_methods(mock_session)


@patch("agenttg.api.md_table_to_png")
def test_image_mode_falls_back_to_rich(mock_png, mock_session):
    mock_png.side_effect = RuntimeError("pandoc not found")
    agenttg.send_reply_markdown(
        "TOKEN", "123", BODY_WITH_TABLE, session=mock_session, table_mode="image"
    )
    assert "sendRichMessage" in _posted_methods(mock_session)


@patch("agenttg.api.md_table_to_png")
def test_rich_mode_falls_back_to_image_then_code_block(mock_png, mock_session):
    """Rich rejected by Telegram and no PNG toolchain -> raw code block."""
    mock_png.side_effect = RuntimeError("pandoc not found")

    def post(url, *args, **kwargs):
        return _error_response() if url.endswith("/sendRichMessage") else _ok_response()

    mock_session.post.side_effect = post
    agenttg.send_reply_markdown(
        "TOKEN", "123", BODY_WITH_TABLE, session=mock_session, table_mode="rich"
    )
    methods = _posted_methods(mock_session)
    assert methods.count("sendRichMessage") == 1
    mock_png.assert_called_once()
    table_message = mock_session.post.call_args_list[2].kwargs["json"]["text"]
    assert table_message.startswith("```")
    assert "| A | B |" in table_message


@patch("agenttg.api.md_table_to_png")
def test_code_mode_touches_neither_renderer(mock_png, mock_session):
    agenttg.send_reply_markdown(
        "TOKEN", "123", BODY_WITH_TABLE, session=mock_session, table_mode="code"
    )
    mock_png.assert_not_called()
    assert _posted_methods(mock_session) == ["sendMessage", "sendMessage", "sendMessage"]


@patch("agenttg.api.md_table_to_png")
def test_oversized_table_skips_rich_api_call(mock_png, mock_session):
    """A table beyond the rich limits must not cost a round trip."""
    mock_png.side_effect = RuntimeError("pandoc not found")
    cols = rich_message.RICH_TABLE_COLUMN_LIMIT + 3
    header = "|" + "|".join(f" c{i} " for i in range(cols)) + "|"
    delim = "|" + "|".join("---" for _ in range(cols)) + "|"
    agenttg.send_reply_markdown(
        "TOKEN", "123", f"{header}\n{delim}", session=mock_session, table_mode="rich"
    )
    assert "sendRichMessage" not in _posted_methods(mock_session)
    assert _posted_methods(mock_session) == ["sendMessage"]


@patch("agenttg.api.md_table_to_png")
def test_env_var_drives_send_reply_markdown(mock_png, mock_session, monkeypatch):
    monkeypatch.setenv(table_modes.TABLE_MODE_ENV, "rich")
    agenttg.send_reply_markdown("TOKEN", "123", BODY_WITH_TABLE, session=mock_session)
    mock_png.assert_not_called()
    assert "sendRichMessage" in _posted_methods(mock_session)
