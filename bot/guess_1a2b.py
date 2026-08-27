import random
from collections import Counter

from telegram import Update
from telegram.ext import ContextTypes

DIGITS = "0123456789"
ANSWER_LENGTH = 4

GAME_STATE_KEYS = ("ab_active", "ab_answer", "ab_count")


def _generate_answer() -> str:
    return "".join(random.sample(DIGITS, ANSWER_LENGTH))


def _reset_game(chat_data):
    for key in GAME_STATE_KEYS:
        chat_data.pop(key, None)


def _calc_ab(guess: str, answer: str) -> tuple[int, int]:
    a = sum(1 for g, ans in zip(guess, answer) if g == ans)
    # 剩下沒對到位置的數字才拿來算 B，用 Counter 避免同一個答案數字被重複比對命中
    remaining_guess = Counter(g for g, ans in zip(guess, answer) if g != ans)
    remaining_answer = Counter(ans for g, ans in zip(guess, answer) if g != ans)
    b = sum(min(count, remaining_answer[digit]) for digit, count in remaining_guess.items())
    return a, b


async def guess_1a2b_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_data = context.chat_data

    if chat_data.get("ab_active"):
        await update.message.reply_text("1A2B還在進行中啦！繼續猜猜看那個數字吧汪！")
        return

    chat_data["ab_active"] = True
    chat_data["ab_answer"] = _generate_answer()
    chat_data["ab_count"] = 0
    await update.message.reply_text(
        "歐拉～壽司小狼要來跟你玩1A2B啦！🐺\n\n"
        "我心裡已經想好一個數字不重複的四位數字了（每一位都是0~9），你猜猜看是多少？\n\n"
        "數字對、位置也對 > A\n"
        "數字對、位置不對 > B\n\n"
        "猜出4A就贏啦，快猜猜看汪！"
    )


async def rule_guess_1a2b(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    chat_data = context.chat_data
    if not chat_data.get("ab_active"):
        return

    guess = text.strip()
    if len(guess) != ANSWER_LENGTH or not guess.isdigit():
        await update.message.reply_text("只能輸入不重複的四位數字啦汪！")
        return True

    chat_data["ab_count"] += 1
    answer = chat_data["ab_answer"]
    a, b = _calc_ab(guess, answer)

    if a == ANSWER_LENGTH:
        count = chat_data["ab_count"]
        _reset_game(chat_data)
        await update.message.reply_text(
            f"賓果，答案就是{answer}！你總共猜了{count}次，太厲害啦～🎉"
        )
        return True

    await update.message.reply_text(f"{a}A{b}B，再猜猜看！")
    return True


async def stop_1a2b_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_data = context.chat_data
    if not chat_data.get("ab_active"):
        await update.message.reply_text("目前沒有進行中的1A2B遊戲唷！")
        return

    answer = chat_data["ab_answer"]
    _reset_game(chat_data)
    await update.message.reply_text(f"好啦好啦，遊戲中止！公布答案，剛剛的數字其實是{answer}。")
