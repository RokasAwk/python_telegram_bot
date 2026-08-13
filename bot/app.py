from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from .basic_commands import help_command, start, website
from .callbacks import error_handler, handle_callback_query
from .config import BOT_TOKEN, logger
from .duel import ATTACK_CALLBACK_DATA, attack_command, handle_attack_callback, stop_command
from .text_dispatch import handle_text
from .weather import handle_weather_city_callback, handle_weather_period_callback, weather

# 顯示在 Telegram 輸入框旁「/」選單裡的指令說明，跟 chat_rules.rule_capability 的介紹保持一致
BOT_COMMANDS = [
    BotCommand("start", "跟我打招呼"),
    BotCommand("help", "顯示常用問句選單"),
    BotCommand("website", "壽司狼哥哥的網站連結"),
    BotCommand("weather", "查詢台灣各縣市天氣"),
    BotCommand("attack", "攻擊荒野猛獸，開始決鬥"),
    BotCommand("stop", "中止正在進行的決鬥"),
]


async def _register_commands(app: Application):
    await app.bot.set_my_commands(BOT_COMMANDS)


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "找不到 BOT_TOKEN，請在同一目錄建立 .env 檔，內容為：\nBOT_TOKEN=你的token"
        )

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(_register_commands).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("website", website))
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(CommandHandler("attack", attack_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(
        CallbackQueryHandler(handle_attack_callback, pattern=f"^{ATTACK_CALLBACK_DATA}$")
    )
    app.add_handler(CallbackQueryHandler(handle_weather_city_callback, pattern=r"^weather:city:"))
    app.add_handler(CallbackQueryHandler(handle_weather_period_callback, pattern=r"^weather:period:"))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    logger.info("Bot 啟動中，開始用 long polling 監聽訊息...")
    app.run_polling()
