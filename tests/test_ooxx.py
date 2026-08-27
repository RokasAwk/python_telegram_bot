from unittest.mock import AsyncMock

import pytest

from bot.ooxx import (
    AI_MARK,
    EMPTY,
    USER_MARK,
    _fallback_move,
    _is_full,
    _winner,
    handle_ooxx_again_callback,
    handle_ooxx_move_callback,
    ooxx_command,
    rule_ooxx,
    stop_ooxx_command,
)


def _board(spec: str) -> list[str]:
    """把 "OX. .O. ..X" 這種字串轉成 9 格盤面，'.' 代表空格。"""
    return [EMPTY if ch == "." else ch for ch in spec.replace(" ", "")]


# ---- 純函式 -------------------------------------------------------------


@pytest.mark.parametrize(
    "spec",
    ["OOO ... ...", "... XXX ...", "O.. O.. O..", "..X .X. X..", "X.. .X. ..X"],
)
def test_winner_detects_every_line_orientation(spec):
    board = _board(spec)
    assert _winner(board) == board[next(i for i, c in enumerate(board) if c != EMPTY)]


def test_winner_returns_none_when_no_line():
    assert _winner(_board("OX. .O. ..X")) is None


def test_is_full_only_true_with_no_empty_cells():
    assert _is_full(_board("OXO XOX XOO"))
    assert not _is_full(_board("OXO XOX XO."))


def test_fallback_move_takes_the_winning_cell():
    # X 只要下 2 就連成第一列
    assert _fallback_move(_board("XX. OO. ...")) == 2


def test_fallback_move_blocks_opponent_when_cannot_win():
    # X 贏不了（兩子不同線），必須擋掉 O 的第一列
    assert _fallback_move(_board("OO. X.. ..X")) == 2


def test_fallback_move_prefers_center_then_corner():
    assert _fallback_move(_board("... ... ...")) == 4
    assert _fallback_move(_board("... .O. ...")) == 0


# ---- /ooxx 起手 -------------------------------------------------------


async def test_ooxx_command_starts_game_and_sends_grid_only_as_buttons(make_update, make_context):
    update = make_update(text="/ooxx")
    context = make_context()

    await ooxx_command(update, context)

    assert context.chat_data["ooxx_active"] is True
    assert context.chat_data["ooxx_board"] == [EMPTY] * 9
    (text,), kwargs = update.message.reply_text.call_args
    assert "來玩OOXX" in text
    # 訊息內文不帶九宮格，格子狀態只呈現在按鈕上
    assert "｜" not in text
    buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert [b.callback_data for b in buttons] == [f"ooxx:move:{i}" for i in range(9)]
    assert [b.text for b in buttons] == ["１", "２", "３", "４", "５", "６", "７", "８", "９"]


async def test_ooxx_command_refuses_when_game_already_running(make_update, make_context):
    update = make_update(text="/ooxx")
    context = make_context()
    context.chat_data.update({"ooxx_active": True, "ooxx_board": [EMPTY] * 9})

    await ooxx_command(update, context)

    (text,), _ = update.message.reply_text.call_args
    assert "沒下完" in text


async def test_rule_ooxx_matches_case_insensitively(make_update, make_context):
    update = make_update(text="ooxx")
    context = make_context()

    handled = await rule_ooxx(update, context, "ooxx")

    assert handled is True
    assert context.chat_data["ooxx_active"] is True


async def test_rule_ooxx_ignores_unrelated_text(make_update, make_context):
    handled = await rule_ooxx(make_update(text="哈囉"), make_context(), "哈囉")
    assert handled is None


# ---- 下棋 callback ---------------------------------------------------


async def test_move_on_occupied_cell_nags_and_does_not_advance(make_callback_update, make_context):
    update = make_callback_update("ooxx:move:0")
    context = make_context()
    context.chat_data.update({"ooxx_active": True, "ooxx_board": _board("O.. ... ...")})

    await handle_ooxx_move_callback(update, context)

    (msg,), _ = update.callback_query.answer.call_args
    assert "換一格" in msg
    context.bot.send_message.assert_not_called()
    assert context.chat_data["ooxx_board"] == _board("O.. ... ...")


async def test_move_when_game_over_only_pops_ended_toast(make_callback_update, make_context):
    update = make_callback_update("ooxx:move:0")
    context = make_context()
    # 結束訊息上的最終盤面按鈕還在，但遊戲已非進行中
    context.chat_data.update({"ooxx_active": False, "ooxx_board": _board("OOO XX. ...")})

    await handle_ooxx_move_callback(update, context)

    (msg,), _ = update.callback_query.answer.call_args
    assert "已經結束" in msg and "/ooxx" in msg
    context.bot.send_message.assert_not_called()
    assert update.callback_query.answer.await_args.kwargs.get("show_alert") in (None, False)


async def test_valid_move_places_o_then_asks_ai_and_places_x(make_callback_update, make_context, mocker):
    mocker.patch("bot.ooxx.ask_ooxx_move", new=AsyncMock(return_value=4))
    update = make_callback_update("ooxx:move:0")
    context = make_context()
    context.chat_data.update({"ooxx_active": True, "ooxx_board": _board("... ... ...")})

    await handle_ooxx_move_callback(update, context)

    board = context.chat_data["ooxx_board"]
    assert board[0] == USER_MARK
    assert board[4] == AI_MARK
    args, kwargs = context.bot.send_message.call_args
    # 內文只講「下在第幾格」，不畫盤面
    assert "｜" not in args[1]
    grid = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert grid[0].text == "⭕" and grid[4].text == "❌"
    assert grid[1].text == "２"


async def test_ai_illegal_answer_falls_back_to_local_strategy(make_callback_update, make_context, mocker):
    # AI 回傳已被佔用的格子 -> 應改用 _fallback_move
    mocker.patch("bot.ooxx.ask_ooxx_move", new=AsyncMock(return_value=0))
    update = make_callback_update("ooxx:move:1")
    context = make_context()
    context.chat_data.update({"ooxx_active": True, "ooxx_board": _board("O.. ... ...")})

    await handle_ooxx_move_callback(update, context)

    board = context.chat_data["ooxx_board"]
    assert board[1] == USER_MARK
    assert board.count(AI_MARK) == 1
    assert board[0] == USER_MARK  # 沒有被覆蓋


async def test_user_winning_move_ends_game_by_editing_buttons_not_a_message(
    make_callback_update, make_context, mocker
):
    ask_mock = mocker.patch("bot.ooxx.ask_ooxx_move", new=AsyncMock())
    update = make_callback_update("ooxx:move:2")
    update.callback_query.edit_message_reply_markup = AsyncMock()
    context = make_context()
    context.chat_data.update({"ooxx_active": True, "ooxx_board": _board("OO. .XX ...")})

    await handle_ooxx_move_callback(update, context)

    ask_mock.assert_not_called()  # 使用者贏了就不該再問 AI
    assert context.chat_data["ooxx_active"] is False
    context.bot.send_message.assert_not_called()  # 結果不用訊息呈現
    markup = update.callback_query.edit_message_reply_markup.await_args.kwargs["reply_markup"]
    keyboard = markup.inline_keyboard
    # 前三排照樣用按鈕呈現最終盤面，最後一排是離開／再來一場
    assert [b.callback_data for row in keyboard[:3] for b in row] == [f"ooxx:move:{i}" for i in range(9)]
    assert keyboard[0][2].text == "⭕"  # 使用者剛下的致勝格
    assert [b.text for b in keyboard[-1]] == ["離開", "再來一場！"]


async def test_ai_winning_move_ends_game_by_editing_buttons(make_callback_update, make_context, mocker):
    mocker.patch("bot.ooxx.ask_ooxx_move", new=AsyncMock(return_value=8))
    update = make_callback_update("ooxx:move:3")
    update.callback_query.edit_message_reply_markup = AsyncMock()
    context = make_context()
    context.chat_data.update({"ooxx_active": True, "ooxx_board": _board("..X .OX O..")})

    await handle_ooxx_move_callback(update, context)

    assert context.chat_data["ooxx_active"] is False
    context.bot.send_message.assert_not_called()
    keyboard = update.callback_query.edit_message_reply_markup.await_args.kwargs["reply_markup"].inline_keyboard
    assert keyboard[-1][0].callback_data == "ooxx:again:no"
    assert keyboard[2][2].text == "❌"  # AI 剛下的致勝格 (index 8)


async def test_full_board_without_winner_is_a_draw(make_callback_update, make_context, mocker):
    mocker.patch("bot.ooxx.ask_ooxx_move", new=AsyncMock())
    update = make_callback_update("ooxx:move:8")
    update.callback_query.edit_message_reply_markup = AsyncMock()
    context = make_context()
    # 使用者下最後一格 8 就填滿，且沒有任何連線
    context.chat_data.update({"ooxx_active": True, "ooxx_board": _board("OXO OXX XO.")})

    await handle_ooxx_move_callback(update, context)

    assert context.chat_data["ooxx_active"] is False
    context.bot.send_message.assert_not_called()
    keyboard = update.callback_query.edit_message_reply_markup.await_args.kwargs["reply_markup"].inline_keyboard
    assert [b.text for b in keyboard[-1]] == ["離開", "再來一場！"]
    assert set(b.text for row in keyboard[:3] for b in row) == {"⭕", "❌"}  # 盤面填滿


# ---- 再來一場 / 離開 -------------------------------------------------


async def test_play_again_yes_starts_fresh_game_and_destroys_buttons(make_callback_update, make_context):
    update = make_callback_update("ooxx:again:yes")
    update.callback_query.edit_message_reply_markup = AsyncMock()
    context = make_context()
    context.chat_data.update({"ooxx_active": False, "ooxx_board": _board("OOO XX. ...")})

    await handle_ooxx_again_callback(update, context)

    update.callback_query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
    assert context.chat_data["ooxx_active"] is True
    assert context.chat_data["ooxx_board"] == [EMPTY] * 9
    assert context.bot.send_message.call_args.kwargs["reply_markup"] is not None


async def test_play_again_no_clears_state_and_destroys_buttons(make_callback_update, make_context):
    update = make_callback_update("ooxx:again:no")
    update.callback_query.edit_message_reply_markup = AsyncMock()
    context = make_context()
    context.chat_data.update({"ooxx_active": False, "ooxx_board": _board("OOO XX. ...")})

    await handle_ooxx_again_callback(update, context)

    update.callback_query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
    assert "ooxx_active" not in context.chat_data
    assert "ooxx_board" not in context.chat_data


# ---- /stopooxx -----------------------------------------------------


async def test_stop_ooxx_command_cancels_active_game(make_update, make_context):
    update = make_update(text="/stopooxx")
    context = make_context()
    context.chat_data.update({"ooxx_active": True, "ooxx_board": [EMPTY] * 9})

    await stop_ooxx_command(update, context)

    assert "ooxx_active" not in context.chat_data
    assert "ooxx_board" not in context.chat_data
    update.message.reply_text.assert_awaited_once()


async def test_stop_ooxx_command_replies_when_nothing_running(make_update, make_context):
    update = make_update(text="/stopooxx")
    context = make_context()

    await stop_ooxx_command(update, context)

    (text,), _ = update.message.reply_text.call_args
    assert "沒有" in text
