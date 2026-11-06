import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import ReplyKeyboardRemove
from telegram.constants import ChatType

import bot.sudoku as sudoku
from bot.sudoku import (
    format_duration,
    handle_sudoku_web_app_data,
    parse_result,
    rule_sudoku,
    stop_sudoku_command,
    sudoku_command,
)

URL = "https://example.github.io/sushi-wolf-miniapp/sudoku/"


@pytest.fixture(autouse=True)
def _webapp_url(monkeypatch):
    monkeypatch.setattr(sudoku, "SUDOKU_WEBAPP_URL", URL)


def _private(update):
    update.effective_chat.type = ChatType.PRIVATE
    return update


# ---- 純函式 -------------------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(42, "42 秒"), (125, "2 分 5 秒"), (3725, "1 小時 2 分 5 秒")],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected


def test_parse_result_accepts_valid_payload():
    assert parse_result(json.dumps({"game": "sudoku", "level": "hard", "seconds": 300})) == ("hard", 300)


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        json.dumps({"game": "ooxx", "level": "easy", "seconds": 10}),
        json.dumps({"game": "sudoku", "level": "insane", "seconds": 10}),
        json.dumps({"game": "sudoku", "level": "easy", "seconds": "10"}),
        json.dumps({"game": "sudoku", "level": "easy", "seconds": True}),
        json.dumps({"game": "sudoku", "level": "easy", "seconds": 0}),
        json.dumps({"game": "sudoku", "level": "easy", "seconds": 10**9}),
    ],
)
def test_parse_result_rejects_bad_payload(raw):
    assert parse_result(raw) is None


# ---- /sudoku ------------------------------------------------------------


async def test_sudoku_command_sends_web_app_keyboard_in_private(make_update, make_context):
    update = _private(make_update(text="/sudoku"))

    await sudoku_command(update, make_context())

    _, kwargs = update.message.reply_text.call_args
    (button,) = [b for row in kwargs["reply_markup"].keyboard for b in row]
    assert button.web_app.url == URL


async def test_sudoku_command_in_group_asks_for_private_chat(make_update, make_context):
    update = make_update(text="/sudoku")
    update.effective_chat.type = ChatType.GROUP

    await sudoku_command(update, make_context())

    (text,), kwargs = update.message.reply_text.call_args
    assert "私訊" in text
    assert "reply_markup" not in kwargs


async def test_sudoku_command_without_url(monkeypatch, make_update, make_context):
    monkeypatch.setattr(sudoku, "SUDOKU_WEBAPP_URL", "")
    update = _private(make_update(text="/sudoku"))

    await sudoku_command(update, make_context())

    (text,), kwargs = update.message.reply_text.call_args
    assert "準備中" in text
    assert "reply_markup" not in kwargs


async def test_rule_sudoku_only_matches_keyword(make_update, make_context):
    assert await rule_sudoku(_private(make_update(text="數獨")), make_context(), "數獨") is True
    assert await rule_sudoku(make_update(text="來玩數獨吧"), make_context(), "來玩數獨吧") is None


async def test_stop_sudoku_removes_keyboard(make_update, make_context):
    update = make_update(text="/stopsudoku")
    await stop_sudoku_command(update, make_context())
    _, kwargs = update.message.reply_text.call_args
    assert isinstance(kwargs["reply_markup"], ReplyKeyboardRemove)


# ---- Mini App 傳回成績 ----------------------------------------------------


def _web_app_update(make_update, data: str):
    update = make_update()
    message = MagicMock()
    message.web_app_data.data = data
    message.reply_text = AsyncMock()
    update.effective_message = message
    return update


async def test_web_app_data_announces_result(make_update, make_context):
    update = _web_app_update(make_update, json.dumps({"game": "sudoku", "level": "normal", "seconds": 125}))

    await handle_sudoku_web_app_data(update, make_context())

    (text,), _ = update.effective_message.reply_text.call_args
    assert "小明" in text
    assert "普通" in text
    assert "2 分 5 秒" in text


async def test_web_app_data_ignores_garbage(make_update, make_context):
    update = _web_app_update(make_update, "garbage")

    await handle_sudoku_web_app_data(update, make_context())

    update.effective_message.reply_text.assert_not_awaited()
