from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_nickname"] = True
    await update.message.reply_text(
        f"你好，{update.effective_user.first_name}！之後想讓我怎麼稱呼你呢？"
    )


async def rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_nickname"] = True
    await update.message.reply_text("好啊，那我要叫你什麼呢？")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup(
        [["壽司小狼是誰？", "這個機器人可以幹嘛？"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text(
        f"{update.effective_user.first_name} 有什麼需要嗎？", reply_markup=keyboard
    )


async def website(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Potato Media",
                    url="https://www.potatomedia.co/users/89ef5e47-ef0a-466c-ba5c-37a4952457be",
                ),
                InlineKeyboardButton(
                    "FaceBook",
                    url="https://www.facebook.com/ying.quguang?mibextid=LQQJ4d",
                ),
            ]
        ]
    )
    await update.message.reply_text("這邊是壽司狼哥哥的網站！", reply_markup=keyboard)
