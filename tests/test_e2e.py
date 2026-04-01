"""End-to-end tests that send real Telegram messages.

These tests require TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.
Run with: pytest -m e2e
"""

from __future__ import annotations

import pytest

import agenttg

pytestmark = pytest.mark.e2e


FINAL_OUTPUT_MESSAGE = """
[E2E TEST] agenttg library integration test.

## Summary

### Best model per benchmark (all experiments)

| Benchmark | Best model | Score |
|-----------|-----------|-------|
| ARC | ft_emb scaled (Job 4) | **50.03** |
| HellaSwag | ft_emb POC (Job 2) | **30.23** (baseline 1B: 30.13) |
| MMLU | original 1B | **40.80** (both fine-tunes regress) |
| MMLU-Pro | ft_linear_proj scaled (Job 3) | **10.28** |

### Key findings

1. **POC collapse (Job 1) was a training-stability artefact, not an architectural failure.**
2. **MMLU regression is the dominant concern at 10k steps.**
3. **Linear projection shows a consistent MMLU-Pro advantage** (+0.56 vs plain embeddings).

### Recommended next steps

1. **Evaluate intermediate checkpoints (2k, 5k steps)** of the scaled runs.
2. **Explicitly zero-init the `linear` layer** and re-run the POC.
"""


def test_send_reply_plain_text(telegram_token, telegram_chat_id):
    """Send a plain text message and verify success."""
    result = agenttg.send_reply(telegram_token, telegram_chat_id, "[agenttg e2e] Plain text test")
    assert len(result) >= 1
    for resp in result:
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


def test_send_reply_markdown(telegram_token, telegram_chat_id):
    """Send a MarkdownV2 formatted message with tables and verify success."""
    result = agenttg.send_reply_markdown(
        telegram_token, telegram_chat_id, FINAL_OUTPUT_MESSAGE.strip()
    )
    assert len(result) >= 1
    for resp in result:
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


def test_send_reply_html(telegram_token, telegram_chat_id):
    """Send an HTML formatted message and verify success."""
    html = "<b>[agenttg e2e]</b> HTML test with <i>italic</i> and <code>code</code>"
    result = agenttg.send_reply_html(telegram_token, telegram_chat_id, html)
    assert len(result) >= 1
    for resp in result:
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


def test_fetch_bot_username(telegram_token):
    """Fetch bot username via getMe API."""
    username = agenttg.fetch_bot_username(telegram_token)
    assert username is not None
    assert len(username) > 0
