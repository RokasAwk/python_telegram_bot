import asyncio

import pytest

from bot.duel import (
    ATTACK_CALLBACK_DATA,
    attack_command,
    handle_attack_callback,
    rule_duel,
    run_duel,
    skill_effect_text,
    stop_command,
)


@pytest.mark.parametrize(
    "atk, expected",
    [
        (100, "打出致命一擊"),
        (70, "打出致命一擊"),
        (69, "效果顯著"),
        (50, "效果顯著"),
        (49, "效果不太明顯"),
        (10, "效果不太明顯"),
        (9, "沒什麼效果"),
        (0, "沒什麼效果"),
    ],
)
def test_skill_effect_text_thresholds(atk, expected):
    assert skill_effect_text(atk) == expected


async def test_run_duel_ignores_call_when_already_in_game(make_context):
    context = make_context()
    context.chat_data["in_game"] = True

    await run_duel(context, chat_id=1, name="小明")

    context.bot.send_message.assert_not_called()


async def test_run_duel_bot_defeated_in_one_hit_sends_victory_message(make_context, mocker):
    mocker.patch("bot.duel.asyncio.sleep", new=mocker.AsyncMock())
    mocker.patch("bot.duel.random.randint", return_value=500)
    context = make_context()

    await run_duel(context, chat_id=1, name="小明")

    last_call = context.bot.send_message.await_args_list[-1]
    assert last_call.args == (1, "荒野猛獸倒下了！你贏得了這場決鬥！")
    assert "reply_markup" in last_call.kwargs
    assert context.chat_data["in_game"] is False
    assert "duel_task" not in context.chat_data


async def test_run_duel_cancellation_sends_stop_message_and_resets_state(make_context, mocker):
    async def cancel_immediately(*args, **kwargs):
        raise asyncio.CancelledError

    mocker.patch("bot.duel.asyncio.sleep", side_effect=cancel_immediately)
    context = make_context()

    with pytest.raises(asyncio.CancelledError):
        await run_duel(context, chat_id=1, name="小明")

    last_call = context.bot.send_message.await_args_list[-1]
    assert last_call.args == (1, "決鬥已中止！")
    assert context.chat_data["in_game"] is False


async def test_attack_command_starts_background_duel_task(make_update, make_context, mocker):
    run_duel_mock = mocker.patch("bot.duel.run_duel", new=mocker.AsyncMock())
    update = make_update()
    context = make_context()

    await attack_command(update, context)
    await asyncio.sleep(0)  # 讓 create_task 排進去的工作有機會執行

    run_duel_mock.assert_awaited_once_with(context, update.effective_chat.id, update.effective_user.first_name)
    assert "duel_task" in context.chat_data


async def test_handle_attack_callback_answers_query_and_starts_duel(make_callback_update, make_context, mocker):
    mocker.patch("bot.duel.run_duel", new=mocker.AsyncMock())
    update = make_callback_update(ATTACK_CALLBACK_DATA)
    context = make_context()

    await handle_attack_callback(update, context)
    await asyncio.sleep(0)

    update.callback_query.answer.assert_awaited_once()
    assert "duel_task" in context.chat_data


async def test_rule_duel_matches_exact_text_and_starts_duel(make_update, make_context, mocker):
    mocker.patch("bot.duel.run_duel", new=mocker.AsyncMock())
    update = make_update(text="攻擊")

    handled = await rule_duel(update, make_context(), "攻擊")
    await asyncio.sleep(0)

    assert handled is True


async def test_rule_duel_ignores_unrelated_text(make_update, make_context):
    handled = await rule_duel(make_update(text="哈囉"), make_context(), "哈囉")
    assert handled is None


async def test_stop_command_cancels_running_task(make_update, make_context):
    update = make_update()
    context = make_context()

    async def never_ends():
        await asyncio.sleep(100)

    task = asyncio.create_task(never_ends())
    context.chat_data["duel_task"] = task

    await stop_command(update, context)
    await asyncio.sleep(0)

    assert task.cancelled() or task.cancelling() > 0
    update.message.reply_text.assert_not_called()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_stop_command_replies_when_no_duel_running(make_update, make_context):
    update = make_update()
    context = make_context()

    await stop_command(update, context)

    update.message.reply_text.assert_awaited_once_with("目前沒有進行中的決鬥可以中止。")


async def test_stop_command_replies_when_task_already_done(make_update, make_context):
    update = make_update()
    context = make_context()

    async def noop():
        return

    task = asyncio.create_task(noop())
    await task
    context.chat_data["duel_task"] = task

    await stop_command(update, context)

    update.message.reply_text.assert_awaited_once_with("目前沒有進行中的決鬥可以中止。")
