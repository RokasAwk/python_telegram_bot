import pytest

from bot.basic_commands import help_command, rename, social_media, start


async def test_start_greets_user_by_first_name(make_update, make_context):
    update = make_update(text="/start")
    context = make_context()

    await start(update, context)

    update.message.reply_text.assert_awaited_once()
    (text,), _ = update.message.reply_text.call_args
    assert "小明" in text


async def test_start_sets_awaiting_nickname_flag(make_update, make_context):
    update = make_update(text="/start")
    context = make_context()

    await start(update, context)

    assert context.user_data["awaiting_nickname"] is True


async def test_rename_sets_awaiting_nickname_flag(make_update, make_context):
    update = make_update(text="/rename")
    context = make_context()

    await rename(update, context)

    assert context.user_data["awaiting_nickname"] is True
    update.message.reply_text.assert_awaited_once()


async def test_help_command_sends_reply_keyboard_with_two_options(make_update, make_context):
    update = make_update(text="/help")
    context = make_context()

    await help_command(update, context)

    update.message.reply_text.assert_awaited_once()
    _, kwargs = update.message.reply_text.call_args
    row = kwargs["reply_markup"].keyboard[0]
    assert [button.text for button in row] == ["壽司小狼是誰？", "這個機器人可以幹嘛？"]


async def test_social_media_sends_four_link_buttons(make_update, make_context):
    update = make_update(text="/social_media")
    context = make_context()

    await social_media(update, context)

    _, kwargs = update.message.reply_text.call_args
    rows = kwargs["reply_markup"].inline_keyboard
    buttons = [button for row in rows for button in row]
    assert [b.text for b in buttons] == ["📘 FaceBook", "🐦 Plurk", "𝕏 嵐瑾 & 拓格", "𝕏 Riku & Hayate"]
    assert all(b.url for b in buttons)
