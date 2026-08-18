import random

from telegram import Update
from telegram.ext import ContextTypes

from .config import STICKER_ID

EAT_OPTIONS = [
    "炒飯", "滷味", "義大利麵", "超商", "麥當勞", "肯德基", "壽司",
    "雞肉飯", "當歸鴨", "火鍋", "鍋貼", "鐵板燒", "拉麵", "牛肉麵", "健康餐", "鹹酥雞", "豆花", "烤肉飯", "魷魚羹", "牛排", "鹹水雞", "飯", "麵",
]
DRINK_OPTIONS = [
    "茶湯會", "清原", "萬波", "珍煮丹", "可不可", "迷客夏",
    "麻古", "清心", "50嵐", "五桐號",
]
LUCK_OPTIONS = ["大吉", "中吉", "小吉", "吉", "凶", "小凶", "大凶", "還是算了吧"]
SLEEP_TRIGGERS = ["睡覺", "睏"]


# 問事：依序比對關鍵字，命中哪一類就從對應的兩個選項隨機回一個
ORACLE_RULES = [
    ("該", ["該", "不該"]),
    ("要", ["要", "不要"]),
    ("能", ["能", "不能"]),
    ("想", ["想", "不想"]),
    ("願意", ["願意", "不願意"]),
    ("可以", ["可以", "不可以"]),
    ("會", ["會", "不會"]),
    ("對", ["對", "不對"]),
]


async def rule_identity(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if text != "壽司小狼是誰？":
        return
    await update.message.reply_text(
        "我是壽司狼的小弟，我叫壽司小狼！\n\n"
        "壽司狼是我大哥！\n\n"
        "我還在努力學習成為一隻實用的狼，我會盡量很可愛❤️"
    )
    return True


async def rule_capability(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if text != "這個機器人可以幹嘛？":
        return
    await update.message.reply_text(
        "嗨！很高興你問我會什麼？\n\n"
        "你可以跟我聊天看看！\n\n"
        "你也可以考慮抖內我，或許我也可以考慮跟你聊更多？\n\n"
        "以下是我聽得懂的斜線指令：\n"
        "/start - 跟我打招呼\n"
        "/rename - 改變我對你的稱呼\n"
        "/help - 顯示常用問句選單\n"
        "/social_media - 壽司狼哥哥的社群連結\n"
        "/weather - 查詢台灣各縣市天氣\n"
        "/mrt - 查詢捷運車站出入口\n"
        "/mrtfare - 查詢捷運票價\n"
        "/attack - 攻擊荒野猛獸，開始決鬥\n"
        "/stop - 中止正在進行的決鬥"
    )
    return True


async def rule_no_sleep(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if not any(trigger in text for trigger in SLEEP_TRIGGERS):
        return
    await update.message.reply_text("睡屁睡，起來嗨！")
    await context.bot.send_sticker(
        update.effective_chat.id,
        STICKER_ID,
        reply_to_message_id=update.message.message_id,
    )
    return True


async def rule_food(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if text != "今天吃什麼":
        return
    name = update.effective_user.first_name
    await update.message.reply_text(f"{name}，你今天吃{random.choice(EAT_OPTIONS)}！")
    return True


async def rule_drink(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if text != "今天喝什麼":
        return
    name = update.effective_user.first_name
    await update.message.reply_text(f"{name}，你今天喝{random.choice(DRINK_OPTIONS)}！")
    return True


async def rule_fortune(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if text != "運勢":
        return
    name = update.effective_user.first_name
    await update.message.reply_text(f"{name}，你今天的運勢是{random.choice(LUCK_OPTIONS)}！")
    return True


async def rule_oracle(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if "小狼" not in text:
        return
    for keyword, options in ORACLE_RULES:
        if keyword in text:
            await update.message.reply_text(random.choice(options))
            return True
    await update.message.reply_text("你還是問天吧")
    return True


async def rule_refuse(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if "不要" not in text:
        return
    if "要不要" in text:
        await update.message.reply_text("嫑")
    else:
        await update.message.reply_text("要")
    return True

