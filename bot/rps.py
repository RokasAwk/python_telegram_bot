import random

from telegram import Update
from telegram.ext import ContextTypes

RPS_OPTIONS = ["剪刀", "石頭", "布"]
RPS_RESULT_TEXT = {0: "平手！", 1: "你輸了！", 2: "你贏了！"}


async def rule_rps(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if text not in RPS_OPTIONS:
        return
    bot_choice = random.choice(RPS_OPTIONS)
    await update.message.reply_text(f"我出{bot_choice}！")

    user_idx = RPS_OPTIONS.index(text)
    bot_idx = RPS_OPTIONS.index(bot_choice)
    diff = (bot_idx - user_idx) % 3
    await update.message.reply_text(RPS_RESULT_TEXT[diff])

    win_times = context.chat_data.get("win_times", 0)
    if diff == 2:
        win_times += 1
    context.chat_data["win_times"] = win_times

    if win_times == 3:
        await update.message.reply_text("好啊！都這樣啊！都給你玩就好了啊")
        context.chat_data["win_times"] = 0
