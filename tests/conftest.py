"""Pytest fixtures and configuration for agenttg tests."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def telegram_token():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        pytest.skip("TELEGRAM_BOT_TOKEN not set")
    return token


E2E_TEST_CHAT_ID = "-5112432786"


@pytest.fixture
def telegram_chat_id():
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", E2E_TEST_CHAT_ID)
    if not chat_id:
        pytest.skip("TELEGRAM_CHAT_ID not set")
    return chat_id
