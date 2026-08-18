import pytest

from bot.chat_rules import (
    DRINK_OPTIONS,
    EAT_OPTIONS,
    LUCK_OPTIONS,
    ORACLE_RULES,
    rule_capability,
    rule_drink,
    rule_food,
    rule_fortune,
    rule_identity,
    rule_no_sleep,
    rule_oracle,
    rule_refuse,
)
from bot.config import STICKER_ID


async def test_rule_identity_matches_exact_text(make_update, make_context):
    update = make_update(text="壽司小狼是誰？")
    handled = await rule_identity(update, make_context(), update.message.text)

    assert handled is True
    update.message.reply_text.assert_awaited_once()


async def test_rule_identity_ignores_unrelated_text(make_update, make_context):
    update = make_update(text="隨便說點什麼")
    handled = await rule_identity(update, make_context(), update.message.text)

    assert handled is None
    update.message.reply_text.assert_not_called()


async def test_rule_capability_lists_slash_commands(make_update, make_context):
    update = make_update(text="這個機器人可以幹嘛？")
    handled = await rule_capability(update, make_context(), update.message.text)

    assert handled is True
    (text,), _ = update.message.reply_text.call_args
    for command in ["/start", "/rename", "/help", "/social_media", "/weather", "/mrt", "/mrtfare", "/attack", "/stop"]:
        assert command in text


@pytest.mark.parametrize("text", ["睡覺", "好睏喔", "睏"])
async def test_rule_no_sleep_matches_any_trigger_and_sends_sticker(make_update, make_context, text):
    update = make_update(text=text)
    context = make_context()

    handled = await rule_no_sleep(update, context, text)

    assert handled is True
    update.message.reply_text.assert_awaited_once_with("睡屁睡，起來嗨！")
    context.bot.send_sticker.assert_awaited_once()
    args, kwargs = context.bot.send_sticker.call_args
    assert args[1] == STICKER_ID


async def test_rule_no_sleep_ignores_unrelated_text(make_update, make_context):
    update = make_update(text="早安")
    context = make_context()

    handled = await rule_no_sleep(update, context, "早安")

    assert handled is None
    context.bot.send_sticker.assert_not_called()


async def test_rule_food_replies_with_name_and_one_of_the_options(make_update, make_context, mocker):
    mocker.patch("bot.chat_rules.random.choice", return_value=EAT_OPTIONS[0])
    update = make_update(text="今天吃什麼")

    handled = await rule_food(update, make_context(), "今天吃什麼")

    assert handled is True
    update.message.reply_text.assert_awaited_once_with(f"小明，你今天吃{EAT_OPTIONS[0]}！")


async def test_rule_drink_replies_with_name_and_one_of_the_options(make_update, make_context, mocker):
    mocker.patch("bot.chat_rules.random.choice", return_value=DRINK_OPTIONS[0])
    update = make_update(text="今天喝什麼")

    handled = await rule_drink(update, make_context(), "今天喝什麼")

    assert handled is True
    update.message.reply_text.assert_awaited_once_with(f"小明，你今天喝{DRINK_OPTIONS[0]}！")


async def test_rule_fortune_replies_with_name_and_one_of_the_options(make_update, make_context, mocker):
    mocker.patch("bot.chat_rules.random.choice", return_value=LUCK_OPTIONS[0])
    update = make_update(text="運勢")

    handled = await rule_fortune(update, make_context(), "運勢")

    assert handled is True
    update.message.reply_text.assert_awaited_once_with(f"小明，你今天的運勢是{LUCK_OPTIONS[0]}！")


async def test_rule_oracle_ignores_text_without_trigger_word(make_update, make_context):
    update = make_update(text="今天天氣如何")
    handled = await rule_oracle(update, make_context(), "今天天氣如何")

    assert handled is None
    update.message.reply_text.assert_not_called()


@pytest.mark.parametrize("keyword, options", ORACLE_RULES)
async def test_rule_oracle_matches_first_keyword_hit(make_update, make_context, mocker, keyword, options):
    mocker.patch("bot.chat_rules.random.choice", return_value=options[0])
    text = f"小狼我{keyword}嗎"

    handled = await rule_oracle(make_update(text=text), make_context(), text)

    assert handled is True


async def test_rule_oracle_falls_back_when_no_keyword_matches(make_update, make_context):
    text = "小狼在嗎"  # 含「小狼」但不含任何 ORACLE_RULES 關鍵字
    update = make_update(text=text)

    handled = await rule_oracle(update, make_context(), text)

    assert handled is True
    update.message.reply_text.assert_awaited_once_with("你還是問天吧")


async def test_rule_refuse_with_yao_bu_yao_replies_niao(make_update, make_context):
    text = "要不要吃飯"
    update = make_update(text=text)

    handled = await rule_refuse(update, make_context(), text)

    assert handled is True
    update.message.reply_text.assert_awaited_once_with("嫑")


async def test_rule_refuse_with_plain_refusal_replies_yao(make_update, make_context):
    text = "不要啦"
    update = make_update(text=text)

    handled = await rule_refuse(update, make_context(), text)

    assert handled is True
    update.message.reply_text.assert_awaited_once_with("要")


async def test_rule_refuse_ignores_text_without_keyword(make_update, make_context):
    update = make_update(text="好啊")
    handled = await rule_refuse(update, make_context(), "好啊")

    assert handled is None
    update.message.reply_text.assert_not_called()
