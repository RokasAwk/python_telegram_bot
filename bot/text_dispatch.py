from telegram import Update
from telegram.ext import ContextTypes

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
from .rps import rule_rps

# 依序執行，允許同一則訊息命中多條規則（對應原本 PHP 一連串獨立 if 的行為）
TEXT_RULES = [
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
    for rule in TEXT_RULES:
        await rule(update, context, text)
