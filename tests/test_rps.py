import pytest

from bot.rps import rule_rps


async def test_rule_rps_ignores_non_rps_text(make_update, make_context):
    update = make_update(text="你好")
    handled = await rule_rps(update, make_context(), "你好")

    assert handled is None
    update.message.reply_text.assert_not_called()


async def test_rule_rps_tie(make_update, make_context, mocker):
    mocker.patch("bot.rps.random.choice", return_value="剪刀")
    update = make_update(text="剪刀")
    context = make_context()

    handled = await rule_rps(update, context, "剪刀")

    assert handled is True
    assert update.message.reply_text.await_args_list[0].args == ("我出剪刀！",)
    assert update.message.reply_text.await_args_list[1].args == ("平手！",)
    assert context.chat_data["win_times"] == 0


async def test_rule_rps_user_loses(make_update, make_context, mocker):
    # bot 出石頭，玩家出剪刀 -> 玩家輸
    mocker.patch("bot.rps.random.choice", return_value="石頭")
    update = make_update(text="剪刀")
    context = make_context()

    await rule_rps(update, context, "剪刀")

    assert update.message.reply_text.await_args_list[1].args == ("你輸了！",)
    assert context.chat_data["win_times"] == 0


async def test_rule_rps_user_wins(make_update, make_context, mocker):
    # bot 出剪刀，玩家出石頭 -> 玩家贏
    mocker.patch("bot.rps.random.choice", return_value="剪刀")
    update = make_update(text="石頭")
    context = make_context()

    await rule_rps(update, context, "石頭")

    assert update.message.reply_text.await_args_list[1].args == ("你贏了！",)
    assert context.chat_data["win_times"] == 1


async def test_rule_rps_third_win_triggers_taunt_and_resets_counter(make_update, make_context, mocker):
    mocker.patch("bot.rps.random.choice", return_value="剪刀")
    context = make_context()
    context.chat_data["win_times"] = 2
    update = make_update(text="石頭")

    await rule_rps(update, context, "石頭")

    assert update.message.reply_text.await_args_list[-1].args == (
        "好啊！都這樣啊！都給你玩就好了啊",
    )
    assert context.chat_data["win_times"] == 0
