from bot.guess_1a2b import guess_1a2b_command, rule_guess_1a2b, stop_1a2b_command


async def test_guess_1a2b_command_starts_new_game(make_update, make_context, mocker):
    mocker.patch("bot.guess_1a2b.random.sample", return_value=list("1874"))
    update = make_update()
    context = make_context()

    await guess_1a2b_command(update, context)

    assert context.chat_data["ab_active"] is True
    assert context.chat_data["ab_answer"] == "1874"
    assert context.chat_data["ab_count"] == 0
    update.message.reply_text.assert_awaited_once()


async def test_guess_1a2b_command_when_already_active_reports_in_progress(make_update, make_context):
    update = make_update()
    context = make_context()
    context.chat_data.update({"ab_active": True, "ab_answer": "1874", "ab_count": 2})

    await guess_1a2b_command(update, context)

    update.message.reply_text.assert_awaited_once_with("1A2B還在進行中啦！繼續猜猜看那個數字吧汪！")
    # 不應該重設既有的遊戲狀態
    assert context.chat_data["ab_answer"] == "1874"
    assert context.chat_data["ab_count"] == 2


async def test_rule_guess_1a2b_ignores_when_no_game_active(make_update, make_context):
    handled = await rule_guess_1a2b(make_update(text="1234"), make_context(), "1234")
    assert handled is None


async def test_rule_guess_1a2b_rejects_non_four_digit_input(make_update, make_context):
    update = make_update(text="哈囉")
    context = make_context()
    context.chat_data.update({"ab_active": True, "ab_answer": "1874", "ab_count": 0})

    handled = await rule_guess_1a2b(update, context, "哈囉")

    assert handled is True
    update.message.reply_text.assert_awaited_once_with("只能輸入不重複的四位數字啦汪！")
    assert context.chat_data["ab_count"] == 0


async def test_rule_guess_1a2b_rejects_wrong_length_number(make_update, make_context):
    update = make_update(text="123")
    context = make_context()
    context.chat_data.update({"ab_active": True, "ab_answer": "1874", "ab_count": 0})

    handled = await rule_guess_1a2b(update, context, "123")

    assert handled is True
    update.message.reply_text.assert_awaited_once_with("只能輸入不重複的四位數字啦汪！")
    assert context.chat_data["ab_count"] == 0


async def test_rule_guess_1a2b_reports_a_and_b_hints(make_update, make_context):
    # 對應題目範例：答案 1874，猜 1728 → 1A2B
    update = make_update(text="1728")
    context = make_context()
    context.chat_data.update({"ab_active": True, "ab_answer": "1874", "ab_count": 0})

    handled = await rule_guess_1a2b(update, context, "1728")

    assert handled is True
    assert context.chat_data["ab_count"] == 1
    update.message.reply_text.assert_awaited_once_with("1A2B，再猜猜看！")


async def test_rule_guess_1a2b_correct_guess_wins_and_resets_state(make_update, make_context):
    update = make_update(text="1874")
    context = make_context()
    context.chat_data.update({"ab_active": True, "ab_answer": "1874", "ab_count": 2})

    handled = await rule_guess_1a2b(update, context, "1874")

    assert handled is True
    update.message.reply_text.assert_awaited_once_with("賓果，答案就是1874！你總共猜了3次，太厲害啦～🎉")
    assert "ab_active" not in context.chat_data
    assert "ab_answer" not in context.chat_data
    assert "ab_count" not in context.chat_data


async def test_stop_1a2b_command_cancels_active_game_and_reveals_answer(make_update, make_context):
    update = make_update()
    context = make_context()
    context.chat_data.update({"ab_active": True, "ab_answer": "1874", "ab_count": 2})

    await stop_1a2b_command(update, context)

    update.message.reply_text.assert_awaited_once_with("好啦好啦，遊戲中止！公布答案，剛剛的數字其實是1874。")
    assert "ab_active" not in context.chat_data
    assert "ab_answer" not in context.chat_data
    assert "ab_count" not in context.chat_data


async def test_stop_1a2b_command_replies_when_no_game_running(make_update, make_context):
    update = make_update()
    context = make_context()

    await stop_1a2b_command(update, context)

    update.message.reply_text.assert_awaited_once_with("目前沒有進行中的1A2B遊戲唷！")
