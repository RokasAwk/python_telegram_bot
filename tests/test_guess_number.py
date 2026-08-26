from bot.guess_number import GUESS_MAX, GUESS_MIN, guess_command, rule_guess_number, stop_guess_command


async def test_guess_command_starts_new_game(make_update, make_context, mocker):
    mocker.patch("bot.guess_number.random.randint", return_value=123)
    update = make_update()
    context = make_context()

    await guess_command(update, context)

    assert context.chat_data["guess_active"] is True
    assert context.chat_data["guess_answer"] == 123
    assert context.chat_data["guess_low"] == GUESS_MIN
    assert context.chat_data["guess_high"] == GUESS_MAX
    assert context.chat_data["guess_count"] == 0
    update.message.reply_text.assert_awaited_once()


async def test_guess_command_when_already_active_reports_current_range(make_update, make_context):
    update = make_update()
    context = make_context()
    context.chat_data.update(
        {"guess_active": True, "guess_answer": 123, "guess_low": 55, "guess_high": 500, "guess_count": 2}
    )

    await guess_command(update, context)

    update.message.reply_text.assert_awaited_once_with(
        "遊戲還在進行中啦！目前的範圍是介於55~500，繼續猜猜看吧！"
    )
    # 不應該重設既有的遊戲狀態
    assert context.chat_data["guess_answer"] == 123
    assert context.chat_data["guess_count"] == 2


async def test_rule_guess_number_ignores_when_no_game_active(make_update, make_context):
    handled = await rule_guess_number(make_update(text="500"), make_context(), "500")
    assert handled is None


async def test_rule_guess_number_rejects_non_numeric_input(make_update, make_context):
    update = make_update(text="哈囉")
    context = make_context()
    context.chat_data.update({"guess_active": True, "guess_answer": 123, "guess_low": 1, "guess_high": 1000, "guess_count": 0})

    handled = await rule_guess_number(update, context, "哈囉")

    assert handled is True
    update.message.reply_text.assert_awaited_once_with("只能輸入1~1000之間的數字啦汪！")
    assert context.chat_data["guess_count"] == 0


async def test_rule_guess_number_rejects_out_of_range_input(make_update, make_context):
    update = make_update(text="10")
    context = make_context()
    context.chat_data.update({"guess_active": True, "guess_answer": 123, "guess_low": 55, "guess_high": 500, "guess_count": 1})

    handled = await rule_guess_number(update, context, "10")

    assert handled is True
    update.message.reply_text.assert_awaited_once_with("只能輸入55~500之間的數字啦汪！")
    assert context.chat_data["guess_count"] == 1


async def test_rule_guess_number_too_high_narrows_upper_bound(make_update, make_context):
    update = make_update(text="500")
    context = make_context()
    context.chat_data.update({"guess_active": True, "guess_answer": 123, "guess_low": 1, "guess_high": 1000, "guess_count": 0})

    handled = await rule_guess_number(update, context, "500")

    assert handled is True
    assert context.chat_data["guess_low"] == 1
    assert context.chat_data["guess_high"] == 500
    assert context.chat_data["guess_count"] == 1
    update.message.reply_text.assert_awaited_once_with("範圍是介於1~500，再猜猜看！")


async def test_rule_guess_number_too_low_narrows_lower_bound(make_update, make_context):
    update = make_update(text="55")
    context = make_context()
    context.chat_data.update({"guess_active": True, "guess_answer": 123, "guess_low": 1, "guess_high": 500, "guess_count": 1})

    handled = await rule_guess_number(update, context, "55")

    assert handled is True
    assert context.chat_data["guess_low"] == 55
    assert context.chat_data["guess_high"] == 500
    assert context.chat_data["guess_count"] == 2
    update.message.reply_text.assert_awaited_once_with("範圍是介於55~500，再猜猜看！")


async def test_rule_guess_number_correct_guess_wins_and_resets_state(make_update, make_context):
    update = make_update(text="123")
    context = make_context()
    context.chat_data.update({"guess_active": True, "guess_answer": 123, "guess_low": 55, "guess_high": 500, "guess_count": 2})

    handled = await rule_guess_number(update, context, "123")

    assert handled is True
    update.message.reply_text.assert_awaited_once_with("賓果！答案就是123！你總共猜了3次，太厲害啦～🎉")
    assert "guess_active" not in context.chat_data
    assert "guess_answer" not in context.chat_data
    assert "guess_low" not in context.chat_data
    assert "guess_high" not in context.chat_data
    assert "guess_count" not in context.chat_data


async def test_stop_guess_command_cancels_active_game_and_reveals_answer(make_update, make_context):
    update = make_update()
    context = make_context()
    context.chat_data.update({"guess_active": True, "guess_answer": 123, "guess_low": 55, "guess_high": 500, "guess_count": 2})

    await stop_guess_command(update, context)

    update.message.reply_text.assert_awaited_once_with("好啦好啦，遊戲中止！公布答案，剛剛的數字其實是123。")
    assert "guess_active" not in context.chat_data
    assert "guess_answer" not in context.chat_data
    assert "guess_low" not in context.chat_data
    assert "guess_high" not in context.chat_data
    assert "guess_count" not in context.chat_data


async def test_stop_guess_command_replies_when_no_game_running(make_update, make_context):
    update = make_update()
    context = make_context()

    await stop_guess_command(update, context)

    update.message.reply_text.assert_awaited_once_with("目前沒有進行中的終極密碼遊戲唷！")
