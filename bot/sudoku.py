"""
數獨 Mini App 的 bot 端。

遊戲本體是靜態網頁，放在另一個公開 repo RokasAwk/sushi-wolf-miniapp 的 sudoku/index.html
（部署在 GitHub Pages），出題、驗證都在前端做。
bot 只負責：
1. /sudoku 時送出一顆開啟 Mini App 的鍵盤按鈕
2. 玩家完成後，Mini App 透過 sendData 把成績傳回來，bot 在聊天室公布

Telegram 限制：只有「鍵盤按鈕（KeyboardButton）」開啟的 Mini App 才能用 sendData，
而且 web_app 鍵盤按鈕只能在私訊裡用，所以群組裡會請大家私訊 bot。
"""
import json

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, WebAppInfo
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from .config import SUDOKU_WEBAPP_URL, logger

LEVEL_LABELS = {"easy": "簡單", "normal": "普通", "hard": "困難"}
MAX_SECONDS = 24 * 60 * 60

OPEN_BUTTON_TEXT = "🧩 開始玩數獨"


def _keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(OPEN_BUTTON_TEXT, web_app=WebAppInfo(url=SUDOKU_WEBAPP_URL))]],
        resize_keyboard=True,
        input_field_placeholder="點下面的按鈕開始玩數獨",
    )


def format_duration(seconds: int) -> str:
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} 小時 {minutes} 分 {sec} 秒"
    if minutes:
        return f"{minutes} 分 {sec} 秒"
    return f"{sec} 秒"


async def sudoku_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SUDOKU_WEBAPP_URL:
        await update.message.reply_text("數獨還在準備中，晚點再來玩汪！")
        return

    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("數獨要在私訊裡開啦！來私訊我輸入 /sudoku 就能玩囉～")
        return

    await update.message.reply_text(
        "來玩數獨啦！點下面的「🧩 開始玩數獨」打開遊戲，完成後按「告訴壽司小狼」我就會知道你的成績！",
        reply_markup=_keyboard(),
    )


async def rule_sudoku(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if text.strip() != "數獨":
        return
    await sudoku_command(update, context)
    return True


async def stop_sudoku_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """把數獨的鍵盤按鈕收起來（遊戲進度存在玩家手機上，下次打開還會在）。"""
    await update.message.reply_text(
        "好啦，數獨先收起來，想玩再跟我說 /sudoku！", reply_markup=ReplyKeyboardRemove()
    )


def parse_result(raw: str) -> tuple[str, int] | None:
    """解析 Mini App 傳回來的成績；格式不對（或被亂改）就回傳 None。"""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("game") != "sudoku":
        return None
    level, seconds = data.get("level"), data.get("seconds")
    if level not in LEVEL_LABELS:
        return None
    if not isinstance(seconds, int) or isinstance(seconds, bool) or not 0 < seconds <= MAX_SECONDS:
        return None
    return level, seconds


async def handle_sudoku_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.effective_message.web_app_data.data
    result = parse_result(raw)
    if result is None:
        logger.warning("收到無法解析的 Mini App 資料：%r", raw)
        return

    level, seconds = result
    name = update.effective_user.first_name
    await update.effective_message.reply_text(
        f"🎉 {name} 完成了一局「{LEVEL_LABELS[level]}」數獨，只花了 {format_duration(seconds)}！好厲害汪！\n"
        "想再玩就點下面的按鈕～",
        reply_markup=_keyboard(),
    )
