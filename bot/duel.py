import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

MY_SKILLS = [
    "撞擊", "影子球", "雷劈", "火球", "水槍", "星爆氣流斬", "十字光輝", "煉獄枷鎖",
    "風暴彈", "光束掃射", "空氣擊打", "咒術", "時空夾擊", "風壓刃", "斬擊",
]
BOT_SKILLS = [
    "撞擊", "撕咬", "爪擊", "劈開", "重踏", "重力波", "火焰牙", "雷電牙", "鐵尾",
    "意念爆擊", "能量光束", "戰慄詛咒", "颶風", "泥巴射擊", "虎嘯",
]

ATTACK_CALLBACK_DATA = "attack"
ATTACK_KEYBOARD = InlineKeyboardMarkup(
    [[InlineKeyboardButton("⚔️ 攻擊", callback_data=ATTACK_CALLBACK_DATA)]]
)


def skill_effect_text(atk: int) -> str:
    if atk >= 70:
        return "打出致命一擊"
    if atk >= 50:
        return "效果顯著"
    if atk >= 10:
        return "效果不太明顯"
    return "沒什麼效果"


async def run_duel_round(context: ContextTypes.DEFAULT_TYPE, chat_id: int, name: str):
    chat_data = context.chat_data
    send = context.bot.send_message

    if chat_data.get("in_game"):
        await send(chat_id, "繼續決鬥！")
    else:
        await send(chat_id, "戰鬥開始！")
        chat_data["my_hp"] = 500
        chat_data["bot_hp"] = 500

    my_atk = random.randint(0, 100)
    await send(
        chat_id,
        f"{name}使出 {random.choice(MY_SKILLS)}，{skill_effect_text(my_atk)}，造成{my_atk}點傷害！",
    )
    chat_data["bot_hp"] -= my_atk

    if chat_data["bot_hp"] <= 0:
        await send(chat_id, "荒野猛獸倒下了！")
        chat_data["in_game"] = False
        return

    await send(chat_id, f"荒野猛獸剩下{chat_data['bot_hp']}點生命！")
    chat_data["in_game"] = True

    bot_atk = random.randint(0, 100)
    await send(
        chat_id,
        f"荒野猛獸反擊使出 {random.choice(BOT_SKILLS)}，"
        f"{skill_effect_text(bot_atk)}，造成{name}{bot_atk}點傷害！",
    )
    chat_data["my_hp"] -= bot_atk

    if chat_data["my_hp"] <= 0:
        await send(chat_id, "你倒下了......")
        chat_data["in_game"] = False
    else:
        # 附上攻擊按鈕，之後不用再手打「攻擊」兩個字
        await send(chat_id, f"你剩下{chat_data['my_hp']}點生命！", reply_markup=ATTACK_KEYBOARD)
        chat_data["in_game"] = True


async def attack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_duel_round(context, update.effective_chat.id, update.effective_user.first_name)


async def handle_attack_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await run_duel_round(
        context, update.effective_chat.id, update.effective_user.first_name
    )


async def rule_duel(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if text != "攻擊":
        return
    await run_duel_round(context, update.effective_chat.id, update.effective_user.first_name)
