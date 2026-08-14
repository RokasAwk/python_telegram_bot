import asyncio
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

ROUND_DELAY_SECONDS = 1

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


async def run_duel(context: ContextTypes.DEFAULT_TYPE, chat_id: int, name: str):
    chat_data = context.chat_data
    send = context.bot.send_message

    if chat_data.get("in_game"):
        # 已經有一場決鬥正在自動進行中，忽略重複觸發（例如連點按鈕）
        return

    chat_data["in_game"] = True
    chat_data["my_hp"] = 500
    chat_data["bot_hp"] = 500
    await send(chat_id, "戰鬥開始！（輸入 /stop 可以隨時中止決鬥）")

    try:
        while True:
            my_atk = random.randint(0, 100)
            await send(
                chat_id,
                f"{name}使出 {random.choice(MY_SKILLS)}，{skill_effect_text(my_atk)}，造成{my_atk}點傷害！",
            )
            chat_data["bot_hp"] -= my_atk
            await asyncio.sleep(ROUND_DELAY_SECONDS)

            if chat_data["bot_hp"] <= 0:
                await send(chat_id, "荒野猛獸倒下了！你贏得了這場決鬥！", reply_markup=ATTACK_KEYBOARD)
                return

            await send(chat_id, f"荒野猛獸剩下{chat_data['bot_hp']}點生命！")
            await asyncio.sleep(ROUND_DELAY_SECONDS)

            bot_atk = random.randint(0, 100)
            await send(
                chat_id,
                f"荒野猛獸反擊使出 {random.choice(BOT_SKILLS)}，"
                f"{skill_effect_text(bot_atk)}，造成{name}{bot_atk}點傷害！",
            )
            chat_data["my_hp"] -= bot_atk
            await asyncio.sleep(ROUND_DELAY_SECONDS)

            if chat_data["my_hp"] <= 0:
                await send(chat_id, "你倒下了......荒野猛獸獲勝！", reply_markup=ATTACK_KEYBOARD)
                return

            await send(chat_id, f"你剩下{chat_data['my_hp']}點生命！")
            await asyncio.sleep(ROUND_DELAY_SECONDS)
    except asyncio.CancelledError:
        await send(chat_id, "決鬥已中止！")
        raise
    finally:
        chat_data["in_game"] = False
        chat_data.pop("duel_task", None)


def _start_duel(context: ContextTypes.DEFAULT_TYPE, chat_id: int, name: str):
    # 用背景 task 執行，這樣 /stop 才能在決鬥自動跑的過程中被處理並中止它
    task = asyncio.create_task(run_duel(context, chat_id, name))
    context.chat_data["duel_task"] = task


async def attack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _start_duel(context, update.effective_chat.id, update.effective_user.first_name)


async def handle_attack_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    _start_duel(context, update.effective_chat.id, update.effective_user.first_name)


async def rule_duel(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if text != "攻擊":
        return
    _start_duel(context, update.effective_chat.id, update.effective_user.first_name)
    return True


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task = context.chat_data.get("duel_task")
    if task and not task.done():
        task.cancel()
    else:
        await update.message.reply_text("目前沒有進行中的決鬥可以中止。")
