import random

from telegram import Update
from telegram.ext import ContextTypes

GUESS_MIN = 1
GUESS_MAX = 1000

GAME_STATE_KEYS = ("guess_active", "guess_answer", "guess_low", "guess_high", "guess_count")


def _reset_game(chat_data):
    for key in GAME_STATE_KEYS:
        chat_data.pop(key, None)


async def guess_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_data = context.chat_data

    if chat_data.get("guess_active"):
        await update.message.reply_text(
            f"遊戲還在進行中啦！目前的範圍是介於{chat_data['guess_low']}~{chat_data['guess_high']}，"
            "繼續猜猜看吧！"
        )
        return

    chat_data["guess_active"] = True
    chat_data["guess_answer"] = random.randint(GUESS_MIN, GUESS_MAX)
    chat_data["guess_low"] = GUESS_MIN
    chat_data["guess_high"] = GUESS_MAX
    chat_data["guess_count"] = 0
    await update.message.reply_text(
        "歐拉～壽司小狼要來跟你玩終極密碼啦！🐺\n\n"
        f"我心裡已經想好一個介於{GUESS_MIN}~{GUESS_MAX}之間的數字了，你猜猜看是多少？"
    )


async def rule_guess_number(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    chat_data = context.chat_data
    if not chat_data.get("guess_active"):
        return

    low = chat_data["guess_low"]
    high = chat_data["guess_high"]

    try:
        guess = int(text)
    except ValueError:
        guess = None

    if guess is None or not (low <= guess <= high):
        await update.message.reply_text(f"只能輸入{low}~{high}之間的數字啦汪！")
        return True

    chat_data["guess_count"] += 1
    answer = chat_data["guess_answer"]

    if guess == answer:
        count = chat_data["guess_count"]
        _reset_game(chat_data)
        await update.message.reply_text(
            f"賓果！答案就是{answer}！你總共猜了{count}次，太厲害啦～🎉"
        )
        return True

    if guess < answer:
        chat_data["guess_low"] = guess
    else:
        chat_data["guess_high"] = guess

    await update.message.reply_text(
        f"範圍是介於{chat_data['guess_low']}~{chat_data['guess_high']}，再猜猜看！"
    )
    return True


async def stop_guess_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_data = context.chat_data
    if not chat_data.get("guess_active"):
        await update.message.reply_text("目前沒有進行中的終極密碼遊戲唷！")
        return

    answer = chat_data["guess_answer"]
    _reset_game(chat_data)
    await update.message.reply_text(f"好啦好啦，遊戲中止！公布答案，剛剛的數字其實是{answer}。")
