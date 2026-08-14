from unittest.mock import AsyncMock

from bot.text_dispatch import handle_text


async def test_handle_text_stops_at_first_matching_rule(make_update, make_context, mocker):
    matching_rule = AsyncMock(return_value=True)
    unreachable_rule = AsyncMock(return_value=True)
    mocker.patch("bot.text_dispatch.TEXT_RULES", [matching_rule, unreachable_rule])
    ask_ai_mock = mocker.patch("bot.text_dispatch.ask_ai", new=AsyncMock())
    update = make_update(text="hi")
    context = make_context()

    await handle_text(update, context)

    matching_rule.assert_awaited_once_with(update, context, "hi")
    unreachable_rule.assert_not_called()
    ask_ai_mock.assert_not_called()


async def test_handle_text_tries_rules_in_order_until_one_matches(make_update, make_context, mocker):
    miss = AsyncMock(return_value=None)
    hit = AsyncMock(return_value=True)
    mocker.patch("bot.text_dispatch.TEXT_RULES", [miss, hit])
    mocker.patch("bot.text_dispatch.ask_ai", new=AsyncMock())
    update = make_update(text="hi")

    await handle_text(update, make_context())

    miss.assert_awaited_once()
    hit.assert_awaited_once()


async def test_handle_text_falls_back_to_ai_when_no_rule_matches(make_update, make_context, mocker):
    mocker.patch("bot.text_dispatch.TEXT_RULES", [AsyncMock(return_value=None)])
    mocker.patch("bot.text_dispatch.ask_ai", new=AsyncMock(return_value="AI回覆"))
    update = make_update(text="hi")

    await handle_text(update, make_context())

    update.message.reply_text.assert_awaited_once_with("AI回覆")


async def test_handle_text_stays_silent_when_ai_returns_none(make_update, make_context, mocker):
    mocker.patch("bot.text_dispatch.TEXT_RULES", [AsyncMock(return_value=None)])
    mocker.patch("bot.text_dispatch.ask_ai", new=AsyncMock(return_value=None))
    update = make_update(text="hi")

    await handle_text(update, make_context())

    update.message.reply_text.assert_not_called()


async def test_handle_text_stays_silent_when_ai_returns_empty_string(make_update, make_context, mocker):
    mocker.patch("bot.text_dispatch.TEXT_RULES", [AsyncMock(return_value=None)])
    mocker.patch("bot.text_dispatch.ask_ai", new=AsyncMock(return_value=""))
    update = make_update(text="hi")

    await handle_text(update, make_context())

    update.message.reply_text.assert_not_called()


async def test_handle_text_integration_uses_real_rule_list_for_known_phrase(make_update, make_context):
    """不 mock TEXT_RULES，確認實際串接（handle_text -> chat_rules）沒有接錯。"""
    update = make_update(text="壽司小狼是誰？")

    await handle_text(update, make_context())

    update.message.reply_text.assert_awaited_once()
    (text,), _ = update.message.reply_text.call_args
    assert "壽司小狼" in text
