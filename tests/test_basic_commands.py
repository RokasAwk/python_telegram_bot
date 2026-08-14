import pytest

from bot.basic_commands import help_command, start, website


async def test_start_greets_user_by_first_name(make_update, make_context):
    update = make_update(text="/start")
    context = make_context()

    await start(update, context)

    update.message.reply_text.assert_awaited_once()
    (text,), _ = update.message.reply_text.call_args
    assert "小明" in text


async def test_help_command_sends_reply_keyboard_with_two_options(make_update, make_context):
    update = make_update(text="/help")
    context = make_context()

    await help_command(update, context)

    update.message.reply_text.assert_awaited_once()
    _, kwargs = update.message.reply_text.call_args
    row = kwargs["reply_markup"].keyboard[0]
    assert [button.text for button in row] == ["壽司小狼是誰？", "這個機器人可以幹嘛？"]


async def test_website_sends_two_link_buttons(make_update, make_context):
    update = make_update(text="/website")
    context = make_context()

    await website(update, context)

    _, kwargs = update.message.reply_text.call_args
    buttons = kwargs["reply_markup"].inline_keyboard[0]
    assert [b.text for b in buttons] == ["Potato Media", "FaceBook"]
    assert all(b.url for b in buttons)
