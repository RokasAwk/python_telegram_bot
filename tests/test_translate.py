from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import InlineQuery, User

from bot import translate as tr


@pytest.fixture(autouse=True)
def no_debounce(mocker):
    mocker.patch.object(tr, "INLINE_DEBOUNCE_SECONDS", 0)
    tr._latest_inline_query.clear()


def _inline_update(query_text, query_id="q1", user_id=111):
    inline_query = MagicMock(spec=InlineQuery)
    inline_query.id = query_id
    inline_query.query = query_text
    inline_query.from_user = MagicMock(spec=User)
    inline_query.from_user.id = user_id
    inline_query.answer = AsyncMock()
    update = MagicMock()
    update.inline_query = inline_query
    return update


async def test_trans_jp_with_text_replies_translation(mocker, make_update, make_context):
    translate_mock = mocker.patch.object(tr, "translate", AsyncMock(return_value="今日はいい天気"))
    update = make_update("/trans_jp 今天天氣真好\n第二行")

    await tr.trans_jp_command(update, make_context())

    translate_mock.assert_awaited_once_with("今天天氣真好\n第二行", "日文")
    update.message.reply_text.assert_awaited_once_with("今日はいい天気")


async def test_trans_en_without_text_shows_inline_button(mocker, make_update, make_context):
    translate_mock = mocker.patch.object(tr, "translate", AsyncMock())
    update = make_update("/trans_en@sushi_bot")
    update.message.reply_to_message = None

    await tr.trans_en_command(update, make_context())

    translate_mock.assert_not_awaited()
    markup = update.message.reply_text.call_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].switch_inline_query_current_chat == "en "
    assert markup.inline_keyboard[1][0].switch_inline_query_current_chat == "翻英文 "


async def test_trans_command_translates_replied_message(mocker, make_update, make_context):
    translate_mock = mocker.patch.object(tr, "translate", AsyncMock(return_value="Hello"))
    update = make_update("/trans_en")
    update.message.reply_to_message = MagicMock(text="你好", caption=None)

    await tr.trans_en_command(update, make_context())

    translate_mock.assert_awaited_once_with("你好", "英文")
    update.message.reply_text.assert_awaited_once_with("Hello")


async def test_trans_command_failure_reply(mocker, make_update, make_context):
    mocker.patch.object(tr, "translate", AsyncMock(return_value=None))
    update = make_update("/trans_jp 你好")

    await tr.trans_jp_command(update, make_context())

    update.message.reply_text.assert_awaited_once_with(tr.TRANSLATE_FAILED_REPLY)


async def test_inline_query_returns_translation_article(mocker):
    translate_mock = mocker.patch.object(tr, "translate", AsyncMock(return_value="今日はいい天気"))
    update = _inline_update("jp 今天天氣真好")

    await tr.handle_translate_inline_query(update, MagicMock())

    translate_mock.assert_awaited_once_with("今天天氣真好", "日文")
    results = update.inline_query.answer.call_args.args[0]
    assert len(results) == 1
    assert results[0].input_message_content.message_text == "今日はいい天気"


@pytest.mark.parametrize("query", ["", "jp", "jp   ", "fr 你好", "今天天氣真好", "翻日文 今天天氣真好"])
async def test_inline_query_ignores_invalid_input(mocker, query):
    translate_mock = mocker.patch.object(tr, "translate", AsyncMock())
    update = _inline_update(query)

    await tr.handle_translate_inline_query(update, MagicMock())

    translate_mock.assert_not_awaited()
    update.inline_query.answer.assert_awaited_once_with([], cache_time=0)


async def test_inline_query_skips_when_superseded_by_newer_query(mocker):
    translate_mock = mocker.patch.object(tr, "translate", AsyncMock(return_value="x"))
    update = _inline_update("en 你好", query_id="old")

    async def newer_query_arrives(_):
        tr._latest_inline_query[111] = "new"

    mocker.patch.object(tr.asyncio, "sleep", newer_query_arrives)

    await tr.handle_translate_inline_query(update, MagicMock())

    translate_mock.assert_not_awaited()
    update.inline_query.answer.assert_not_awaited()


def _bot_context(make_context):
    context = make_context()
    context.bot.username = "Sushi_Bot"
    return context


async def test_mention_message_is_translated(mocker, make_update, make_context):
    translate_mock = mocker.patch.object(tr, "translate", AsyncMock(return_value="今日はいい天気"))
    update = make_update()

    handled = await tr.rule_translate_mention(update, _bot_context(make_context), "@sushi_bot jp 今天天氣真好")

    assert handled is True
    translate_mock.assert_awaited_once_with("今天天氣真好", "日文")
    update.message.reply_text.assert_awaited_once_with("今日はいい天気")


async def test_reply_keyword_message_is_translated(mocker, make_update, make_context):
    translate_mock = mocker.patch.object(tr, "translate", AsyncMock(return_value="It's nice weather"))
    update = make_update()

    handled = await tr.rule_translate_mention(update, _bot_context(make_context), "@Sushi_Bot 翻英文 今天天氣真好")

    assert handled is True
    translate_mock.assert_awaited_once_with("今天天氣真好", "英文")
    update.message.reply_text.assert_awaited_once_with("It's nice weather")


@pytest.mark.parametrize("text", ["jp 你好", "@sushi_bot 翻日文", "@sushi_bot 翻韓文 你好", "@sushi_bot", "@sushi_bot jp", "@sushi_bot 你好", "@other_bot jp 你好"])
async def test_mention_rule_ignores_other_messages(mocker, make_update, make_context, text):
    translate_mock = mocker.patch.object(tr, "translate", AsyncMock())
    update = make_update()

    assert not await tr.rule_translate_mention(update, _bot_context(make_context), text)
    translate_mock.assert_not_awaited()
