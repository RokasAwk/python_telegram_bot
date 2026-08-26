from telegram import Update
from telegram.ext import ContextTypes

from .ai import ask_ai
from .chat_rules import (
    rule_capability,
    rule_drink,
    rule_food,
    rule_fortune,
    rule_identity,
    rule_no_sleep,
    rule_oracle,
    rule_refuse,
)
from .duel import rule_duel
from .guess_number import rule_guess_number
from .rps import rule_rps

# 依序執行，允許同一則訊息命中多條規則（對應原本 PHP 一連串獨立 if 的行為）
# rule_guess_number 放最前面：終極密碼進行中時，要把每一則訊息都當成猜測，不能被其他規則搶走
TEXT_RULES = [
    rule_guess_number,
    rule_identity,
    rule_capability,
    rule_no_sleep,
    rule_food,
    rule_drink,
    rule_fortune,
    rule_oracle,
    rule_refuse,
    rule_rps,
    rule_duel,
]


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # /start 詢問完稱呼後，下一則訊息當作暱稱記起來，之後 AI 對話都用這個稱呼
    if context.user_data.get("awaiting_nickname"):
        nickname = text.strip()
        context.user_data["nickname"] = nickname
        context.user_data["awaiting_nickname"] = False
        await update.message.reply_text(f"好，那我以後就叫你「{nickname}」！")
        return

    for rule in TEXT_RULES:
        if await rule(update, context, text):
            return

    # 所有規則都沒命中，才啟用 AI 備援回覆
    user_name = context.user_data.get("nickname") or update.effective_user.first_name
    reply = await ask_ai(text, user_name)
    if reply:
        await update.message.reply_text(reply)
